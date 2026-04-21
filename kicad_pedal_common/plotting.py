"""Layer plotting and kicad-cli helpers.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

# Logical layer name -> kicad-cli layer name
# PTH/NPTH are not valid layer names in KiCad 10 pcb export svg.
# Use export_drill_map_svg() for drill layers instead.
LAYER_MAP: Dict[str, str] = {
    "f_mask": "F.Mask",
    "f_paste": "F.Paste",
    "edge_cuts": "Edge.Cuts",
    "f_silks": "F.SilkS",
}

# Candidate paths checked in order when kicad-cli is not on PATH
_KICAD_CLI_CANDIDATES = [
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    "/usr/local/bin/kicad-cli",
    "/usr/bin/kicad-cli",
]


def find_kicad_cli() -> Optional[str]:
    """Return the path to kicad-cli, or None if not found.

    Search order:
    1. PATH via shutil.which
    2. Hard-coded candidate paths (macOS app bundle, /usr/local/bin, /usr/bin)
    """
    found = shutil.which("kicad-cli")
    if found:
        return found
    return next((c for c in _KICAD_CLI_CANDIDATES if os.path.exists(c)), None)


def export_layer_svg(
    board_path: str,
    layer: str,
    output_path: str,
    kicad_cli: Optional[str] = None,
) -> None:
    """Export a single PCB layer as SVG using kicad-cli.

    Uses --page-size-mode 2 (fit to board bounds) so all exported SVGs share
    the same coordinate system as the board outline.

    Args:
        board_path:  Absolute path to the .kicad_pcb file.
        layer:       kicad-cli layer name, e.g. "F.Mask" or "Edge.Cuts".
                     Use LAYER_MAP to convert from logical names.
        output_path: Destination path for the SVG file.
        kicad_cli:   Path to kicad-cli binary.  If None, find_kicad_cli() is
                     called automatically.

    Raises:
        RuntimeError: kicad-cli was not found, or the export command failed.
    """
    cli = kicad_cli or find_kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli not found. Install KiCad or add kicad-cli to PATH.")

    cmd = [
        cli,
        "pcb",
        "export",
        "svg",
        "--layers",
        layer,
        "--page-size-mode",
        "2",
        "--exclude-drawing-sheet",
        "--black-and-white",
        "--output",
        output_path,
        board_path,
    ]

    env = os.environ.copy()
    # macOS: make sure KiCad's frameworks are reachable
    env.setdefault(
        "DYLD_FRAMEWORK_PATH",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks",
    )
    env.setdefault(
        "DYLD_LIBRARY_PATH",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks",
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0 or not os.path.exists(output_path):
        detail = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
        raise RuntimeError(
            "kicad-cli SVG export failed (exit {}):\n{}".format(
                result.returncode,
                detail[-4000:],
            )
        )


def export_drill_map_svg(
    board_path: str,
    output_dir: str,
    kicad_cli: Optional[str] = None,
) -> Dict[str, str]:
    """Export PTH and NPTH drill maps as SVGs using kicad-cli pcb export drill.

    Returns a dict of logical_name -> output_path for each produced SVG,
    e.g. {"pth_drills": "/tmp/.../boardname-PTH.svg"}.

    The output filenames are determined by kicad-cli (boardname-PTH.svg,
    boardname-NPTH.svg); we glob for them after export.
    """
    cli = kicad_cli or find_kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli not found.")

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        cli,
        "pcb",
        "export",
        "drill",
        "--output",
        output_dir + "/",
        "--generate-map",
        "--map-format",
        "svg",
        board_path,
    ]

    env = os.environ.copy()
    env.setdefault(
        "DYLD_FRAMEWORK_PATH",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks",
    )
    env.setdefault(
        "DYLD_LIBRARY_PATH",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks",
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0:
        detail = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
        raise RuntimeError(
            "kicad-cli drill export failed (exit {}):\n{}".format(
                result.returncode,
                detail[-4000:],
            )
        )

    # Map produced files back to logical names
    logical: Dict[str, str] = {}
    for fname in os.listdir(output_dir):
        if not fname.endswith(".svg"):
            continue
        lower = fname.lower()
        path = os.path.join(output_dir, fname)
        if "-pth" in lower and "npth" not in lower:
            logical["pth_drills"] = path
        elif "npth" in lower:
            logical["npth_drills"] = path
    return logical


# ---------------------------------------------------------------------------
# Footprint library resolution
# ---------------------------------------------------------------------------

# Candidate base directories for KiCad's bundled footprint libraries.
_KICAD_FP_DIR_CANDIDATES: List[str] = [
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
    "/usr/share/kicad/footprints",
    "/usr/local/share/kicad/footprints",
]


def _fp_lib_table_candidates(board_path: Optional[str] = None):
    """Yield candidate fp-lib-table file paths, most-specific first."""
    if board_path:
        local = pathlib.Path(board_path).parent / "fp-lib-table"
        if local.exists():
            yield str(local)

    if platform.system() == "Darwin":
        base = pathlib.Path.home() / "Library" / "Preferences" / "kicad"
    else:
        base = pathlib.Path.home() / ".config" / "kicad"

    if base.exists():
        try:
            ver_dirs = sorted(
                [d for d in base.iterdir() if d.is_dir()],
                key=lambda d: d.name,
                reverse=True,
            )
            for vd in ver_dirs:
                candidate = vd / "fp-lib-table"
                if candidate.exists():
                    yield str(candidate)
        except OSError:
            pass


def _expand_fp_lib_vars(uri: str) -> str:
    """Expand ${KICAD*_FOOTPRINT_DIR} variables in a library URI."""
    for var in (
        "KICAD9_FOOTPRINT_DIR",
        "KICAD8_FOOTPRINT_DIR",
        "KICAD7_FOOTPRINT_DIR",
        "KICAD_FOOTPRINT_DIR",
    ):
        token = "${" + var + "}"
        if token in uri:
            env_val = os.environ.get(var)
            if env_val:
                return uri.replace(token, env_val)
            for cand in _KICAD_FP_DIR_CANDIDATES:
                if os.path.exists(cand):
                    return uri.replace(token, cand)
    return uri


def _lookup_lib_in_table(table_path: str, nickname: str) -> Optional[str]:
    """Parse a KiCad fp-lib-table and return the URI for the given nickname."""
    try:
        with open(table_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    # Each lib entry looks like:  (lib (name "nick") ... (uri "path") ...)
    # Use paren-counting to extract each lib block (handles arbitrary nesting).
    name_pat = re.compile(r'\(name\s+"([^"]+)"\)')
    uri_pat = re.compile(r'\(uri\s+"([^"]+)"\)')

    for m in re.finditer(r"\(lib\b", content):
        depth = 0
        end = m.start()
        for i in range(m.start(), min(m.start() + 4000, len(content))):
            if content[i] == "(":
                depth += 1
            elif content[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        body = content[m.start():end]
        name_m = name_pat.search(body)
        uri_m = uri_pat.search(body)
        if name_m and uri_m and name_m.group(1) == nickname:
            return _expand_fp_lib_vars(uri_m.group(1))
    return None


def resolve_fp_library(nickname: str, board_path: Optional[str] = None) -> Optional[str]:
    """Resolve a footprint library nickname to its .pretty directory path.

    Searches the project-local fp-lib-table first, then the global user table.
    Returns the resolved directory path, or None if not found.
    """
    for table_path in _fp_lib_table_candidates(board_path):
        uri = _lookup_lib_in_table(table_path, nickname)
        if uri and os.path.isdir(uri):
            return uri
    return None


# ---------------------------------------------------------------------------
# Footprint SVG export
# ---------------------------------------------------------------------------


def parse_svg_viewbox(svg_path: str) -> Optional[Tuple[float, float, float, float]]:
    """Return (x, y, width, height) from an SVG file's viewBox attribute, or None."""
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        # The attribute may appear with or without the SVG namespace prefix.
        vb = None
        for attr_name, val in root.attrib.items():
            if attr_name == "viewBox" or attr_name.lower().endswith("}viewbox"):
                vb = val
                break
        if vb:
            parts = vb.strip().split()
            if len(parts) == 4:
                return (
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2]),
                    float(parts[3]),
                )
    except Exception:
        pass
    return None


def parse_svg_content_bbox(svg_path: str) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_x, min_y, max_x, max_y) of all drawn content in an SVG file.

    Parses absolute M/L path commands and circle cx/cy attributes.
    KiCad-generated SVGs use only absolute coordinates so this is sufficient.
    Returns None if the file cannot be parsed or contains no coordinates.
    """
    try:
        with open(svg_path, encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return None

    xs: List[float] = []
    ys: List[float] = []

    # Absolute M/L/C path commands: capture pairs of numbers after M or L
    for m in re.finditer(r"[ML]\s*([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)", data):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))

    # Circle centers
    for m in re.finditer(r'cx="\s*([-+]?\d*\.?\d+)"\s+cy="\s*([-+]?\d*\.?\d+)"', data):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))
    for m in re.finditer(r'cy="\s*([-+]?\d*\.?\d+)"\s+cx="\s*([-+]?\d*\.?\d+)"', data):
        ys.append(float(m.group(1)))
        xs.append(float(m.group(2)))

    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def parse_kicad_pcb_edge_cuts_bbox(
    board_path: str,
) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_x, min_y, max_x, max_y) of the Edge.Cuts layer in a .kicad_pcb file.

    Uses paren-counting to extract each primitive block, then filters by
    "Edge.Cuts".  Handles arbitrary nesting depth (e.g. gr_arc with nested
    stroke sub-blocks).
    Returns None if no edge cuts geometry is found.
    """
    try:
        with open(board_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return None

    xs: List[float] = []
    ys: List[float] = []

    _COORD_RE = re.compile(
        r'\((start|end|mid|center)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\)'
    )
    _PRIM_START = re.compile(
        r'\((gr_line|gr_arc|gr_rect|gr_circle|gr_poly|segment|arc)\b'
    )

    for m in _PRIM_START.finditer(content):
        # Walk forward counting parens to find the end of this block.
        depth = 0
        end = m.start()
        for i in range(m.start(), min(m.start() + 4000, len(content))):
            if content[i] == "(":
                depth += 1
            elif content[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        block = content[m.start() : end]
        if '"Edge.Cuts"' not in block and "'Edge.Cuts'" not in block:
            continue
        for coord_m in _COORD_RE.finditer(block):
            xs.append(float(coord_m.group(2)))
            ys.append(float(coord_m.group(3)))

    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def fix_svg_viewbox(svg_path: str) -> Optional[Tuple[float, float, float, float]]:
    """Rewrite an SVG's viewBox to match the actual content bounding box.

    Returns the new (min_x, min_y, max_x, max_y) bounds, or None if the file
    could not be updated.  The width/height attributes are also updated.
    """
    bbox = parse_svg_content_bbox(svg_path)
    if bbox is None:
        return None

    min_x, min_y, max_x, max_y = bbox
    w = max_x - min_x
    h = max_y - min_y
    if w <= 0 or h <= 0:
        return None

    try:
        with open(svg_path, encoding="utf-8") as fh:
            data = fh.read()

        vb_new = "{:.4f} {:.4f} {:.4f} {:.4f}".format(min_x, min_y, w, h)
        # Replace viewBox attribute value
        data = re.sub(r'viewBox="[^"]*"', 'viewBox="{}"'.format(vb_new), data)
        # Replace width and height attributes
        data = re.sub(r'width="[^"]*mm"', 'width="{:.4f}mm"'.format(w), data)
        data = re.sub(r'height="[^"]*mm"', 'height="{:.4f}mm"'.format(h), data)

        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(data)
    except OSError:
        return None

    return bbox


def parse_svg_edge_cuts_bbox(svg_path: str) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_x, min_y, max_x, max_y) of board content in an edge cuts SVG.

    Filters to x >= 0 to exclude KiCad's page frame elements, which appear at
    negative x coordinates in all KiCad-exported SVGs.
    Returns None if the file cannot be parsed or contains no valid coordinates.
    """
    try:
        with open(svg_path, encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return None

    xs: List[float] = []
    ys: List[float] = []

    for m in re.finditer(r"[ML]\s*([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)", data):
        x = float(m.group(1))
        y = float(m.group(2))
        if x >= 0:
            xs.append(x)
            ys.append(y)

    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def compute_svg_transform(
    board_path: str,
    edge_cuts_svg_path: str,
) -> Dict[str, float]:
    """Compute the translation offset from KiCad absolute (kipy) mm to SVG page coordinates.

    Returns {"offset_x": float, "offset_y": float} where:
        svg_x = kipy_x + offset_x
        svg_y = kipy_y + offset_y

    Uses the board's edge cuts bounding box from both the .kicad_pcb S-expression
    and the exported edge cuts SVG.  Falls back to {"offset_x": 0.0, "offset_y": 0.0}
    if either source cannot be parsed.
    """
    pcb_bbox = parse_kicad_pcb_edge_cuts_bbox(board_path)
    svg_bbox = parse_svg_edge_cuts_bbox(edge_cuts_svg_path)

    if pcb_bbox is None or svg_bbox is None:
        return {"offset_x": 0.0, "offset_y": 0.0}

    return {
        "offset_x": round(svg_bbox[0] - pcb_bbox[0], 4),
        "offset_y": round(svg_bbox[1] - pcb_bbox[1], 4),
    }


def export_footprint_svg(
    library_path: str,
    footprint_name: str,
    layers: str,
    output_path: str,
    kicad_cli: Optional[str] = None,
) -> None:
    """Export a footprint from a .pretty library as an SVG using kicad-cli.

    Args:
        library_path:   Path to the .pretty library directory.
        footprint_name: Footprint name within the library (no library prefix).
        layers:         Comma-separated layer string, e.g. "F.Courtyard,F.Cu,F.Mask".
        output_path:    Destination path for the produced SVG file.
        kicad_cli:      Explicit path to kicad-cli.  None = auto-locate.

    Raises:
        RuntimeError: kicad-cli was not found or the export failed.
    """
    cli = kicad_cli or find_kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli not found. Install KiCad or add kicad-cli to PATH.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [
            cli,
            "fp",
            "export",
            "svg",
            "--black-and-white",
            "--layers",
            layers,
            "--output",
            tmp_dir,
            "--footprint",
            footprint_name,
            library_path,
        ]

        env = os.environ.copy()
        env.setdefault(
            "DYLD_FRAMEWORK_PATH",
            "/Applications/KiCad/KiCad.app/Contents/Frameworks",
        )
        env.setdefault(
            "DYLD_LIBRARY_PATH",
            "/Applications/KiCad/KiCad.app/Contents/Frameworks",
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "kicad-cli fp export svg failed (exit {}): {}".format(
                    result.returncode,
                    result.stderr.strip()[:300],
                )
            )

        # kicad-cli writes <footprint_name>.svg in the output directory.
        expected = os.path.join(tmp_dir, footprint_name + ".svg")
        if not os.path.exists(expected):
            svg_files = [f for f in os.listdir(tmp_dir) if f.endswith(".svg")]
            if not svg_files:
                raise RuntimeError(
                    "kicad-cli fp export produced no SVG files in {}".format(tmp_dir)
                )
            expected = os.path.join(tmp_dir, svg_files[0])

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        shutil.copy2(expected, output_path)
