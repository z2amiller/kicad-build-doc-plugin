"""BoardAdapter protocol and KipyBoardAdapter implementation.

Provides a kipy-independent interface for reading board data so callers
don't depend on kipy directly, enabling future headless/kiutils adapters.

Python 3.9 compatible — no match/case, no |union syntax, no walrus in
type annotations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

NM_PER_MM = 1_000_000  # kipy uses nanometres


# ---------------------------------------------------------------------------
# Data containers (plain Python — no kipy dependency)
# ---------------------------------------------------------------------------


@dataclass
class FootprintData:
    """Plain-Python representation of a single footprint.

    All callers should treat ``_raw`` as opaque — it holds the underlying
    kipy / kiutils footprint object and is used internally by the adapter.
    """

    ref: str
    value: str
    footprint_id: str       # "LibName:FpName"
    layer: str              # "F" or "B"
    pos_x: float            # mm
    pos_y: float            # mm
    rotation: float         # degrees 0-360 CCW
    dnp: bool
    exclude_from_bom: bool
    # Opaque reference to the underlying fp object; not shown in repr.
    _raw: object = field(default=None, repr=False, compare=False)


@dataclass
class BBoxCenter:
    """Bounding-box centre in mm."""

    cx_mm: float
    cy_mm: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class BoardAdapter:
    """Protocol describing the minimal board interface needed by manifest-creator.

    Implementations wrap a concrete board object (kipy, kiutils, …) and
    expose only the data needed by the plugin so that the plugin code
    stays free of any direct kipy dependency.

    This is written as a regular base class with NotImplementedError rather
    than typing.Protocol so it is usable without importing the typing extras
    module at runtime, and remains compatible with Python 3.9.
    """

    def get_footprints(self) -> List[FootprintData]:
        """Return all footprints on the board as a list of :class:`FootprintData`."""
        raise NotImplementedError

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        """Return the bounding-box centre for *fp_data*, or None if unavailable."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# KipyBoardAdapter
# ---------------------------------------------------------------------------


class KipyBoardAdapter(BoardAdapter):
    """BoardAdapter implementation that wraps a live kipy board object."""

    def __init__(self, board: object) -> None:
        self._board = board

    # ------------------------------------------------------------------
    # BoardAdapter interface
    # ------------------------------------------------------------------

    def get_footprints(self) -> List[FootprintData]:
        """Return all footprints from the kipy board as :class:`FootprintData`.

        Footprints with empty or placeholder refs (REF**, ~*) are skipped.
        All error-handling mirrors the original ``get_footprints(board)``
        implementation in ``footprint.py``.
        """
        result: List[FootprintData] = []
        try:
            footprints = list(self._board.get_footprints())
        except Exception:
            return result

        for fp in footprints:
            fp_data = self._parse_footprint(fp)
            if fp_data is not None:
                result.append(fp_data)

        return result

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        """Return the bounding-box centre in mm, or None if unavailable."""
        if fp_data._raw is None:
            return None
        try:
            bb = self._board.get_item_bounding_box(fp_data._raw)
            if bb is None:
                return None
            center = bb.center()
            fp_raw = fp_data._raw
            fp_x = fp_raw.position.x
            fp_y = fp_raw.position.y

            dx_nm = center.x - fp_x
            dy_nm = center.y - fp_y

            cx_mm = dx_nm / NM_PER_MM
            cy_mm = dy_nm / NM_PER_MM
            return BBoxCenter(cx_mm=cx_mm, cy_mm=cy_mm)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_footprint(self, fp: object) -> Optional[FootprintData]:
        """Convert a single kipy footprint object to :class:`FootprintData`.

        Returns None if the footprint should be skipped (empty/placeholder ref,
        or unrecoverable parse error).
        """
        try:
            ref = fp.reference_field.text.value  # type: ignore[union-attr]
        except Exception:
            return None

        if not ref or ref.startswith("~") or ref in ("REF**", ""):
            return None

        try:
            value = fp.value_field.text.value  # type: ignore[union-attr]
        except Exception:
            value = ""

        try:
            fp_id = "{}:{}".format(
                fp.definition.id.library,  # type: ignore[union-attr]
                fp.definition.id.name,     # type: ignore[union-attr]
            )
        except Exception:
            fp_id = ""

        layer = _detect_layer(fp)

        # Position in mm
        try:
            pos_x = fp.position.x / NM_PER_MM  # type: ignore[union-attr]
            pos_y = fp.position.y / NM_PER_MM  # type: ignore[union-attr]
        except Exception:
            pos_x = 0.0
            pos_y = 0.0

        # Rotation: convert from radians, normalize 0-360
        rotation = 0.0
        try:
            rad = fp.orientation.to_radians()  # type: ignore[union-attr]
            rotation = math.degrees(rad) % 360.0
        except Exception:
            rotation = 0.0

        # Attribute flags
        dnp = False
        exclude_from_bom = False
        try:
            attrs = fp.attributes  # type: ignore[union-attr]
            dnp = bool(attrs.do_not_populate)
            exclude_from_bom = bool(attrs.exclude_from_bill_of_materials)
        except Exception:
            pass

        return FootprintData(
            ref=ref,
            value=value,
            footprint_id=fp_id,
            layer=layer,
            pos_x=pos_x,
            pos_y=pos_y,
            rotation=rotation,
            dnp=dnp,
            exclude_from_bom=exclude_from_bom,
            _raw=fp,
        )


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _detect_layer(fp: object) -> str:
    """Return "F" or "B" for a kipy footprint object.

    Mirrors the layer-detection logic in ``footprint.py`` exactly, including
    the numeric-31 fallback needed when kipy is mocked in tests.
    """
    try:
        layer_raw = fp.layer  # type: ignore[union-attr]
        layer_int = layer_raw.value if hasattr(layer_raw, "value") else layer_raw
        if layer_int == 31:
            return "B"
        # Enum check: only compare against real BoardLayer enum (not MagicMock).
        try:
            import inspect

            from kipy.board import BoardLayer  # type: ignore[import]

            if inspect.isclass(BoardLayer) and layer_raw == BoardLayer.BL_B_Cu:
                return "B"
        except Exception:
            pass
    except Exception:
        pass
    return "F"
