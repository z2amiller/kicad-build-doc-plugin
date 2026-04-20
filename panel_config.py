"""Parser for panel_config.json panel configuration files."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


_PRESETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enclosure_presets.json")


def _load_enclosure_presets() -> Dict[str, dict]:
    try:
        with open(_PRESETS_FILE) as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}


# Enclosure preset definitions loaded from enclosure_presets.json.
# Each entry: {"width": float, "height": float, "depth": float,
#              "rotated": bool, "side_b_defaults": [...]}
ENCLOSURE_PRESETS: Dict[str, dict] = _load_enclosure_presets()


@dataclass
class EnclosureConfig:
    width: float
    height: float
    depth: float = 35.0
    preset: Optional[str] = None   # e.g. "125B" or "1590XX-R"; None = custom
    rotated: bool = False           # True for -R presets; Tayda coords are transformed


@dataclass
class FootprintHoleConfig:
    hole_dia: float
    offset_x: float
    offset_y: float
    label: Optional[str] = None
    use_pad_centroid: bool = False


@dataclass
class FixedHole:
    label: str
    dia: float
    x: float
    y: float


@dataclass
class SideBHole:
    """A manually-defined hole on the enclosure top face (Side B)."""
    label: str
    diameter_mm: float
    x_mm: float
    y_mm: float


@dataclass
class SnapConfig:
    """Snap-to-grid configuration for front-face hole positions."""
    radius_mm: float = 0.0            # snap radius; 0 = disabled
    top_row_mm: float = 38.0          # Y of topmost control row above enclosure centre
    x: List[float] = field(default_factory=list)   # snap columns (mm from enc centre)
    y: List[float] = field(default_factory=list)   # snap rows   (mm from enc centre)


@dataclass
class PanelConfig:
    enclosure: EnclosureConfig
    footprints: Dict[str, FootprintHoleConfig]
    fixed_holes: List[FixedHole]
    side_b: List[SideBHole] = field(default_factory=list)
    snap: SnapConfig = field(default_factory=SnapConfig)


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
    preset = d.get("preset") or None
    if preset and preset in ENCLOSURE_PRESETS:
        pdata = ENCLOSURE_PRESETS[preset]
        return EnclosureConfig(
            width=float(d.get("width", pdata["width"])),
            height=float(d.get("height", pdata["height"])),
            depth=float(d.get("depth", pdata["depth"])),
            preset=preset,
            rotated=bool(pdata.get("rotated", False)),
        )
    return EnclosureConfig(
        width=float(d["width"]),
        height=float(d["height"]),
        depth=float(d.get("depth", 35.0)),
        preset=None,
        rotated=False,
    )


def _footprint_from_dict(d: dict) -> FootprintHoleConfig:
    return FootprintHoleConfig(
        hole_dia=float(d["hole_dia"]),
        offset_x=float(d.get("offset_x", 0.0)),
        offset_y=float(d.get("offset_y", 0.0)),
        label=d.get("label") or None,
        use_pad_centroid=bool(d.get("use_pad_centroid", False)),
    )


def _fixed_hole_from_dict(d: dict) -> FixedHole:
    return FixedHole(
        label=str(d["label"]),
        dia=float(d["dia"]),
        x=float(d["x"]),
        y=float(d["y"]),
    )


def _snap_from_dict(d: dict) -> SnapConfig:
    return SnapConfig(
        radius_mm=float(d.get("radius_mm", 0.0)),
        top_row_mm=float(d.get("top_row_mm", 38.0)),
        x=[float(v) for v in d.get("x", [])],
        y=[float(v) for v in d.get("y", [])],
    )


def _side_b_hole_from_dict(d: dict) -> SideBHole:
    return SideBHole(
        label=str(d.get("label", "")),
        diameter_mm=float(d["diameter_mm"]),
        x_mm=float(d["x_mm"]),
        y_mm=float(d["y_mm"]),
    )


def _merge_configs(base: dict, override: dict) -> dict:
    """Merge override into base with section-aware semantics.

    - enclosure: override replaces base entirely if present
    - footprints: dict merge — override entries add/replace individual global entries;
                  set a footprint to null to remove it from the global list
    - fixed_holes: override replaces base entirely if the key is present in override;
                   if absent from override, global list is used unchanged
    """
    result: dict = {}

    result["enclosure"] = override.get("enclosure", base.get("enclosure", {}))
    result["snap"] = override.get("snap", base.get("snap", {}))

    base_fps = base.get("footprints", {})
    override_fps = override.get("footprints", {})
    merged_fps = dict(base_fps)
    for fp_id, cfg in override_fps.items():
        if cfg is None:
            merged_fps.pop(fp_id, None)  # null means "remove from global defaults"
        else:
            merged_fps[fp_id] = cfg
    result["footprints"] = merged_fps

    if "fixed_holes" in override:
        result["fixed_holes"] = list(override["fixed_holes"])
    else:
        result["fixed_holes"] = list(base.get("fixed_holes", []))

    if "side_b" in override:
        result["side_b"] = list(override["side_b"])
    elif "side_b" in base:
        result["side_b"] = list(base["side_b"])

    return result


def load_global_config(plugin_dir: str) -> PanelConfig:
    """Load only the global panel_config.json (no project-level merge)."""
    return load_panel_config("/nonexistent/board.kicad_pcb", plugin_dir)


def snapshot_global_to_project(
    board_path: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
) -> None:
    """Write a project panel_config.json seeded from global defaults if none exists.

    Called before generating the enclosure template so the drill editor always
    has a self-contained project config to open and edit.
    """
    _log = log or (lambda msg: None)
    if not board_path:
        return
    project_dir = os.path.dirname(board_path)
    project_path = os.path.join(project_dir, "panel_config.json")
    if os.path.exists(project_path):
        return  # already has a project config

    global_path = os.path.join(plugin_dir, "panel_config.json")
    if not os.path.exists(global_path):
        return

    try:
        with open(global_path) as fh:
            data = json.load(fh)
        # Strip the internal comment key; the project file is a clean snapshot.
        data.pop("_comment", None)
        with open(project_path, "w") as fh:
            json.dump(data, fh, indent=2)
        _log(f"  Created project panel_config.json from global template.")
    except Exception as exc:
        _log(f"  Warning: could not snapshot panel_config.json: {exc}")


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

    if "side_b" in merged:
        side_b: List[SideBHole] = [_side_b_hole_from_dict(h) for h in merged["side_b"]]
    elif enclosure.preset and enclosure.preset in ENCLOSURE_PRESETS:
        layouts = ENCLOSURE_PRESETS[enclosure.preset].get("side_b_layouts", [])
        first_holes = layouts[0]["holes"] if layouts else []
        side_b = [_side_b_hole_from_dict(h) for h in first_holes]
    else:
        side_b = []

    snap = _snap_from_dict(merged["snap"]) if merged.get("snap") else SnapConfig()

    return PanelConfig(enclosure=enclosure, footprints=footprints, fixed_holes=fixed_holes, side_b=side_b, snap=snap)
