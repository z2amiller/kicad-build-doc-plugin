# KiCad Build Document Generator

Generates a **PedalPCB-style build document PDF** from an open KiCad 9 board.

## What it produces

| Page | Content | Source |
|------|---------|--------|
| Cover | Project name · board outline · controls list | `Edge.Cuts` + `F.SilkS` layers via pcbnew API |
| Parts List | Formatted BOM table (Location / Value / Type / Notes) | Footprint attributes on the board |
| Schematic | Full schematic export | `.kicad_sch` file via `kicad-cli` |

---

## Installation

### 1. Install Python dependencies

Open KiCad's **Scripting Console** (`Tools → Scripting Console`) and run:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install",
                "reportlab", "pypdf", "svglib"], check=True)
```

Or install system-wide / in your venv:

```bash
pip install reportlab pypdf svglib
```

> `svglib` is optional but **strongly recommended** — without it the board outline
> is exported to disk but not embedded in the cover page.

### 2. Copy the plugin

Copy the **entire `kicad_build_doc_plugin/` folder** to your KiCad plugin directory:

| OS | Path |
|----|------|
| Linux | `~/.local/share/kicad/9.0/scripting/plugins/` |
| macOS | `~/Library/Preferences/kicad/9.0/scripting/plugins/` |
| Windows | `%APPDATA%\kicad\9.0\scripting\plugins\` |

### 3. Reload plugins

In KiCad PCB Editor: **Tools → External Plugins → Refresh Plugins**

A **"Build Document Generator"** entry will appear under **Tools → External Plugins**.

---

## Usage

1. Open your `.kicad_pcb` file in the PCB Editor.
2. Run **Tools → External Plugins → Build Document Generator**.
3. Fill in the dialog:
   - **Project Name** – pre-filled from the board filename
   - **Author / Copyright** – e.g. `© 2025 Your Name`
   - **Revision** – version string
   - **Pages to include** – Cover / BOM / Schematic (checkboxes)
   - **Schematic path** – auto-detected if `.kicad_sch` is next to the board
   - **Output PDF** – where to save the document
4. Click **Generate PDF**.

---

## BOM population tips

The parts list pulls from standard KiCad footprint fields:

| PDF column | KiCad field |
|------------|-------------|
| **LOCATION** | `Reference` |
| **VALUE** | `Value` |
| **TYPE** | `Description` field → falls back to footprint name heuristic |
| **NOTES** | `Datasheet` field |

Fill in `Description` and `Datasheet` fields in your schematic symbols for the
richest output. The plugin sorts by reference prefix then number (R1, R2 … C1, C2 …).

### Controls detection

The cover page lists "Controls & Features" by scanning for:
- Footprints whose reference starts with `RV`, `SW`, `POT`, or `ENC`
- Silkscreen text matching common control names (Volume, Tone, Gain, Drive, etc.)

---

## Schematic export

The plugin calls `kicad-cli sch export pdf` — the official KiCad 9 CLI tool.
Make sure `kicad-cli` is on your system `PATH`:

```bash
# Test it:
kicad-cli --version
```

On macOS/Linux it is typically installed alongside KiCad. On Windows it lives in
`C:\Program Files\KiCad\9.0\bin\`.

If `kicad-cli` is not found, the plugin falls back to **kiauto** (`eeschema_do`)
if that is installed. If neither is available, the schematic page is skipped with
a warning.

---

## File structure

```
kicad-build-doc-plugin/
├── __init__.py              # Plugin entry point & ActionPlugin subclass
├── build_doc_dialog.py      # wxPython dialog UI
├── build_doc_generator.py   # Orchestrates PDF assembly
├── cover_page.py            # Cover page: board outline, controls list
├── bom_pages.py             # Parts list / BOM table pages
├── schematic_export.py      # kicad-cli schematic export wrapper
├── footprint_utils.py       # Reference sorting, field extraction helpers
├── pdf_utils.py             # reportlab / pypdf utilities
├── panel_config.py          # Panel layout configuration
├── enclosure_template.py    # Enclosure drill template generation
├── external_footprints.txt  # Known external footprint library references
├── icon.png                 # Plugin toolbar icon
├── metadata.json            # KiCad plugin manager metadata
├── requirements.txt         # Python dependencies
├── LICENSE
└── README.md
```

---

## License

MIT — do whatever you like with it.
