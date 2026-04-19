# KiCad Build Document Generator

Generates a **Build document PDF** directly from an open KiCad 9+ board. The document can include a cover page with the board outline and controls list, a parts list (BOM), an enclosure drilling template at 1:1 scale, and an exported schematic — all merged into a single PDF.

---

## Installation

### Via KiCad Plugin Manager (recommended)

1. Open KiCad → **Plugin and Content Manager**
2. To the right of the repository selector, hit **Manage**
3. Add a new repository: https://raw.githubusercontent.com/z2amiller/kicad-pcm/main/repository.json
4. Select this repository and install the **Build Document Generator**
5. Click **Install**

### Manual installation

Copy the plugin folder to your KiCad scripting plugins directory:

| OS | Path |
|----|------|
| macOS | `~/Library/Preferences/kicad/9.0/scripting/plugins/` |
| Linux | `~/.local/share/kicad/9.0/scripting/plugins/` |
| Windows | `%APPDATA%\kicad\9.0\scripting\plugins\` |

Then in the PCB Editor: **Tools → External Plugins → Refresh Plugins**

### Caveat:  Kicad 10

In KiCad 10.0.0, there's a bug with refreshing plugins into the toolbar.  You have to
manually refresh your plugins to make the toolbar show every time you launch the
PCB editor.  You have to go to **Settings -> PCB Editor -> Plugins** and toggle one
of the visibility checkmarks.

Or even better, upgrade to KiCad 10.0.1 that does not have this bug.

### Python dependencies

The plugin installs its own Python environment automatically via the KiCad Plugin Manager. If you installed manually, open the KiCad Scripting Console (`Tools → Scripting Console`) and run:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install",
                "reportlab", "pypdf", "svglib"], check=True)
```

---

***NOTE*** The first launch after you run this plugin can be slow, since it has
to install these dependencies.

## Basic usage

1. Open your `.kicad_pcb` file in the PCB Editor
2. Click the **Build Doc** toolbar button, or go to **Tools → External Plugins → Build Document Generator**
3. Fill in the dialog (project name, author, revision)
4. Select which pages to include
5. Click **Generate PDF**

---

## Cover page customisation

### Copyright line

Place a plain-text file named **`copyright.txt`** in the plugin's installation directory. Its contents are rendered as a small centred line below the revision/date, in a muted colour. A single line is typical:

```
© 2025 Your Name. All rights reserved.
```

Multi-line files are supported — newlines become line breaks in the PDF.

### Project blurb

A short description of the circuit (what it does, design notes, build tips) can appear between the board image and the controls list. There are two ways to provide it:

**Via the dialog:** Type directly into the **Cover Blurb** text box. The box accepts multiple lines.

**Via file:** Place a plain-text file named **`builddoc_blurb.txt`** in the same directory as your `.kicad_pcb` file. It is loaded automatically and pre-fills the Cover Blurb box each time you open the dialog — where you can edit or clear it before generating.

Keep the blurb to 2–4 sentences. When a blurb is present, the board outline image shrinks slightly (from 55% to 50% of the page height) to make room.

---

## Marking controls with the `Control` field

The cover page lists all controls for the build. The plugin discovers controls by looking for a custom footprint field named **`Control`** — not by reference prefix.

To mark a footprint as a control, add a `Control` field to it in KiCad:

1. Double-click the footprint in the PCB Editor (or select it and press **E**)
2. Go to the **Fields** tab
3. Click **Add Field**
4. Set the field name to `Control` and the value to the label you want to appear in the document — e.g. `Volume`, `Tone`, `Bypass`

The value of the `Control` field is what gets printed in the build document, so use the human-readable name a builder would recognise.

### External vs. internal controls

Controls are split into two groups on the cover page:

- **External** — controls that appear on the enclosure panel (pots, jacks, footswitches, toggle switches). These are footprints listed in `panel_config.json` (see below).
- **Internal** — controls accessible inside the enclosure (trimmers, DIP switches, internal jumpers).

A few component types are automatically excluded from the **internal** list even if they have a `Control` field: test points (`TP*`), LEDs and diodes (`LED*`, `D*`), and single-pad footprints. These are indicators or debug aids, not controls a builder needs to set.

---

## Enclosure drilling template

The plugin can generate a 1:1 scale drilling template for your enclosure — print it, tape it to the enclosure, and use it to mark hole positions before drilling.

Hole positions are determined by the footprint positions on the board, transformed into enclosure coordinates. The plugin needs to know which footprints correspond to panel-mounted components and what hole size each requires. This is configured in a JSON file called **`panel_config.json`**.

### The `panel_config.json` file

The plugin ships with a global default `panel_config.json` covering common footprints. You can add a per-project `panel_config.json` next to your `.kicad_pcb` file — it is **merged** on top of the global defaults, so you only need to specify what differs.

#### File format

```json
{
  "enclosure": {
    "width": 62,
    "height": 117,
    "depth": 35
  },
  "footprints": {
    "LibraryName:FootprintName": {
      "hole_dia": 7.6,
      "offset_x": 0,
      "offset_y": 0,
      "label": "Optional label"
    }
  },
  "fixed_holes": [
    {"label": "Footswitch", "dia": 12.2, "x": 0, "y": -45.2}
  ]
}
```

**`enclosure`** — physical size of the enclosure face in mm. `depth` defaults to 35 if omitted.

**`footprints`** — keyed by the full KiCad footprint ID (`Library:Name`). Each entry has:
- `hole_dia` — drill diameter in mm
- `offset_x`, `offset_y` — shift the hole position relative to the footprint origin (useful when the physical hole is not centred on the KiCad origin)
- `label` — optional; if omitted, the footprint's `Control` field is used, then the reference

**`fixed_holes`** — holes at specific enclosure coordinates, not derived from PCB footprint positions. Coordinates are in mm from the enclosure centre; positive Y is up, positive X is right.

### Merge behaviour

When a per-project `panel_config.json` is present, it is merged with the global defaults:

| Section | Behaviour |
|---------|-----------|
| `enclosure` | Project value replaces global entirely |
| `footprints` | Project entries add or override individual global entries; set a footprint to `null` to remove it; unmentioned footprints are inherited |
| `fixed_holes` | Project entries are appended after global entries |

A minimal per-project file that just changes the enclosure and adds a fixed footswitch hole:

```json
{
  "enclosure": {"width": 112, "height": 60, "depth": 31},
  "fixed_holes": [
    {"label": "Bypass", "dia": 12.2, "x": 0, "y": -22}
  ]
}
```

### How hole positions are calculated

Footprint positions are read from the PCB in millimetres. The plugin:

1. Mirrors the X axis (the panel is viewed from outside, which is the opposite of looking at the PCB front)
2. Anchors the Y axis so the topmost external control row lands 38 mm above the enclosure centre — a reasonable default for most stompbox layouts

The `offset_x` and `offset_y` values are applied **after** this coordinate transform. Use them when a component's mounting hole is not at its KiCad footprint origin — for example, a pot where the mechanical hole is offset from the electrical origin.

### Autodetection: Back-panel LEDs

LEDs mounted on the **back copper layer** (B.Cu) are treated as panel indicators and automatically get a hole in the drilling template — no `panel_config.json` entry required. The default hole diameter is 3.2 mm. To override the size for a specific LED footprint, add it to the `footprints` section.

---

## Parts list (BOM)

The BOM page shows every component on the board except those marked **Do Not Populate**, **Exclude from BOM**, or **Exclude from Position Files** — unless the component has a `Control` field, in which case it is always included.

| Column | Source |
|--------|--------|
| **Location** | `Reference` (or the `Control` field value, if set) |
| **Value** | `Value` field |
| **Type** | `Description` field, or a heuristic based on the reference prefix |
| **Notes** | `Notes` field |

Fill in the `Description` and `Notes` fields on your schematic symbols for the richest output.

---

## Bulk description and notes editor

The plugin includes an editor for setting `Description` and `Notes` fields on multiple components at once, without having to open each footprint individually.

To open it: in the plugin dialog, click **Edit Component Descriptions…**

### How to use it

The editor shows all BOM-visible components. Click any row to select it — the **Description** and **Notes** fields for that component appear in the edit boxes at the bottom of the window and can be edited directly.

**Bulk sync:** Check the checkbox on the left of one or more rows. While a checked row is selected, any edit you make in the Description or Notes box is immediately copied to all other checked rows in the same field. This makes it easy to set the same description on a group of identical resistors or capacitors.

Use **Select All** / **Select None** to quickly check or uncheck everything.

Click **Apply** when you are done. This writes the changes back to the board.

### Important: saving your work

The editor writes field values to the board in memory, but does **not save the board file**. After applying edits:

1. **Save the board** — `Ctrl+S` (or `Cmd+S` on macOS) — to persist the changes to the `.kicad_pcb` file
2. **Push changes back to the schematic** — in the PCB Editor, run **Tools → Update Schematic from PCB…** and enable the "Update fields" option. This keeps your schematic symbols in sync with the footprint fields you edited.

Skipping step 2 is fine if your workflow treats the PCB as the source of truth for `Description` and `Notes`, but doing it keeps everything consistent.

---

## Schematic export

The plugin calls `kicad-cli sch export pdf` to export the schematic. It auto-detects the root schematic from the board filename (same directory, same base name, `.kicad_sch` extension). You can also browse to a different schematic in the dialog.

If `kicad-cli` is not found on your system PATH, the schematic page is skipped with a warning. On macOS, `kicad-cli` is typically at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` and the plugin searches common locations automatically.

---

## License

MIT — see [LICENSE](LICENSE).
