"""Parser for external_footprints.txt panel configuration file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class EnclosureConfig:
    width: float
    height: float
    depth: float = 35.0


@dataclass
class FootprintHoleConfig:
    hole_dia: float
    offset_x: float
    offset_y: float
    label: Optional[str] = None


@dataclass
class FixedHole:
    label: str
    dia: float
    x: float
    y: float


@dataclass
class PanelConfig:
    enclosure: EnclosureConfig
    footprints: Dict[str, FootprintHoleConfig]
    fixed_holes: List[FixedHole]


def load_text_file(filename: str, dirs: List[str]) -> Optional[str]:
    """Return the content of *filename* from the first directory that contains it.

    Strips trailing whitespace. Returns None if not found in any directory.
    """
    for directory in dirs:
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            with open(path) as fh:
                return fh.read().rstrip()
    return None


def load_copyright(plugin_dir: str) -> Optional[str]:
    """Return content of copyright.txt from the plugin directory, or None."""
    return load_text_file("copyright.txt", [plugin_dir])


def load_blurb(project_dir: str) -> Optional[str]:
    """Return content of builddoc_blurb.txt from the project directory, or None."""
    return load_text_file("builddoc_blurb.txt", [project_dir])


def load_panel_config(
    board_path: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
) -> PanelConfig:
    """Parse the panel config from external_footprints.txt.

    Searches the project directory first, then the plugin directory, so that
    per-project overrides shadow the plugin defaults.

    Line formats (all after optional # comments):
      ENCLOSURE  width_mm  height_mm  [depth_mm]
      FIXED      label     hole_dia   x   y
      Lib:Name   hole_dia  offset_x   offset_y  [label]
    """
    _log = log or (lambda msg: None)
    enclosure = EnclosureConfig(width=62, height=117, depth=35.0)
    footprints: Dict[str, FootprintHoleConfig] = {}
    fixed_holes: List[FixedHole] = []

    project_dir = os.path.dirname(board_path)
    for directory in [project_dir, plugin_dir]:
        candidate = os.path.join(directory, "external_footprints.txt")
        if not os.path.exists(candidate):
            continue
        with open(candidate) as fh:
            for raw in fh:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                kw = parts[0].upper()
                if kw == "ENCLOSURE" and len(parts) >= 3:
                    enclosure = EnclosureConfig(
                        width=float(parts[1]),
                        height=float(parts[2]),
                        depth=float(parts[3]) if len(parts) >= 4 else 35.0,
                    )
                elif kw == "FIXED" and len(parts) >= 5:
                    fixed_holes.append(FixedHole(
                        label=parts[1],
                        dia=float(parts[2]),
                        x=float(parts[3]),
                        y=float(parts[4]),
                    ))
                elif ":" in parts[0]:
                    fp_id = parts[0]
                    if len(parts) >= 4:
                        footprints[fp_id] = FootprintHoleConfig(
                            hole_dia=float(parts[1]),
                            offset_x=float(parts[2]),
                            offset_y=float(parts[3]),
                            label=parts[4] if len(parts) >= 5 else None,
                        )
                    else:
                        footprints[fp_id] = FootprintHoleConfig(
                            hole_dia=8.0,
                            offset_x=0.0,
                            offset_y=0.0,
                            label=None,
                        )
        _log(f"  Loaded panel config from {candidate}")
        break

    return PanelConfig(enclosure=enclosure, footprints=footprints, fixed_holes=fixed_holes)
