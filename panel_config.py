"""Parser for external_footprints.txt panel configuration file."""

import os
from typing import Callable, Dict, Optional


def load_panel_config(
    board_path: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
) -> Dict:
    """Parse the panel config from external_footprints.txt.

    Searches the project directory first, then the plugin directory, so that
    per-project overrides shadow the plugin defaults.

    Line formats (all after optional # comments):
      ENCLOSURE  width_mm  height_mm  [depth_mm]
      FIXED      label     hole_dia   x   y
      Lib:Name   hole_dia  offset_x   offset_y  [label]
    """
    _log = log or (lambda msg: None)
    result: Dict = {
        "footprints": {},
        "fixed_holes": [],
        "enclosure": {"width": 62, "height": 117, "depth": 35.0},
    }
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
                    result["enclosure"] = {
                        "width": float(parts[1]),
                        "height": float(parts[2]),
                        "depth": float(parts[3]) if len(parts) >= 4 else 35.0,
                    }
                elif kw == "FIXED" and len(parts) >= 5:
                    result["fixed_holes"].append(
                        {
                            "label": parts[1],
                            "dia": float(parts[2]),
                            "x": float(parts[3]),
                            "y": float(parts[4]),
                        }
                    )
                elif ":" in parts[0]:
                    fp_id = parts[0]
                    if len(parts) >= 4:
                        result["footprints"][fp_id] = {
                            "hole_dia": float(parts[1]),
                            "offset_x": float(parts[2]),
                            "offset_y": float(parts[3]),
                            "label": parts[4] if len(parts) >= 5 else None,
                        }
                    else:
                        result["footprints"][fp_id] = {
                            "hole_dia": 8.0,
                            "offset_x": 0.0,
                            "offset_y": 0.0,
                            "label": None,
                        }
        _log(f"  Loaded panel config from {candidate}")
        break
    return result
