"""Helpers for locating and invoking kicad-cli."""

from __future__ import annotations

import os
from typing import Optional

from kicad_pedal_common.plotting import find_kicad_cli as _common_find_kicad_cli

_kicad_cli_override: Optional[str] = None


def set_kicad_cli_path(path: Optional[str]) -> None:
    """Store the kicad-cli path reported by the KiCad IPC API."""
    global _kicad_cli_override
    _kicad_cli_override = path


def find_kicad_cli() -> Optional[str]:
    """Return the path to kicad-cli, or None if not found.

    Preference order:
    1. Path provided by the KiCad IPC API (set via set_kicad_cli_path)
    2. PATH lookup and hard-coded candidates (delegated to kicad_pedal_common)
    """
    if _kicad_cli_override and os.path.exists(_kicad_cli_override):
        return _kicad_cli_override
    return _common_find_kicad_cli()


def kicad_env() -> dict:
    """Return an os.environ copy with KiCad framework paths set (macOS)."""
    env = os.environ.copy()
    env["DYLD_FRAMEWORK_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    env["DYLD_LIBRARY_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    return env
