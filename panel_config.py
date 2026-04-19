"""Parser for panel_config.json panel configuration files."""
from __future__ import annotations

import json
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


def _parse_json_config(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def _enclosure_from_dict(d: dict) -> EnclosureConfig:
    return EnclosureConfig(
        width=float(d["width"]),
        height=float(d["height"]),
        depth=float(d.get("depth", 35.0)),
    )


def _footprint_from_dict(d: dict) -> FootprintHoleConfig:
    return FootprintHoleConfig(
        hole_dia=float(d["hole_dia"]),
        offset_x=float(d.get("offset_x", 0.0)),
        offset_y=float(d.get("offset_y", 0.0)),
        label=d.get("label") or None,
    )


def _fixed_hole_from_dict(d: dict) -> FixedHole:
    return FixedHole(
        label=str(d["label"]),
        dia=float(d["dia"]),
        x=float(d["x"]),
        y=float(d["y"]),
    )


def _merge_configs(base: dict, override: dict) -> dict:
    """Merge override into base with section-aware semantics.

    - enclosure: override replaces base entirely if present
    - footprints: dict merge — override entries add/replace individual footprints
    - fixed_holes: concatenated (base first, then override additions)
    """
    result: dict = {}

    result["enclosure"] = override.get("enclosure", base.get("enclosure", {}))

    base_fps = base.get("footprints", {})
    override_fps = override.get("footprints", {})
    result["footprints"] = {**base_fps, **override_fps}

    result["fixed_holes"] = list(base.get("fixed_holes", [])) + list(override.get("fixed_holes", []))

    return result


def load_panel_config(
    board_path: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
) -> PanelConfig:
    """Load and merge panel config from panel_config.json files.

    Loads the global default from the plugin directory, then merges any
    per-project panel_config.json found next to the board file on top of it.

    Merge semantics:
      - enclosure: project value replaces global entirely
      - footprints: project entries add/override individual global entries
      - fixed_holes: project entries are appended after global entries
    """
    _log = log or (lambda msg: None)

    global_path = os.path.join(plugin_dir, "panel_config.json")
    project_dir = os.path.dirname(board_path)
    project_path = os.path.join(project_dir, "panel_config.json")

    base: dict = {}
    if os.path.exists(global_path):
        base = _parse_json_config(global_path)
        _log(f"  Loaded global panel config from {global_path}")

    merged = base
    if os.path.exists(project_path):
        project = _parse_json_config(project_path)
        merged = _merge_configs(base, project)
        _log(f"  Merged project panel config from {project_path}")

    enc_dict = merged.get("enclosure")
    enclosure = _enclosure_from_dict(enc_dict) if enc_dict else EnclosureConfig(width=62, height=117, depth=35.0)

    footprints: Dict[str, FootprintHoleConfig] = {
        fp_id: _footprint_from_dict(cfg)
        for fp_id, cfg in merged.get("footprints", {}).items()
    }

    fixed_holes: List[FixedHole] = [
        _fixed_hole_from_dict(h) for h in merged.get("fixed_holes", [])
    ]

    return PanelConfig(enclosure=enclosure, footprints=footprints, fixed_holes=fixed_holes)
