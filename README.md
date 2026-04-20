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

**`enclosure`** — physical size of the enclosure face in mm. `depth` defaults to 35 if omitted. You can also set a `preset` name (see below) and the dimensions will be filled in automatically.

**`footprints`** — keyed by the full KiCad footprint ID (`Library:Name`). Each entry has:
- `hole_dia` — drill diameter in mm
- `offset_x`, `offset_y` — shift the hole position relative to the footprint origin (useful when the physical hole is not centred on the KiCad origin)
- `label` — optional; if omitted, the footprint's `Control` field is used, then the reference

**`fixed_holes`** — holes at specific enclosure coordinates, not derived from PCB footprint positions. Coordinates are in mm from the enclosure centre; positive Y is up, positive X is right.

**`side_b`** — holes on the top face of the enclosure (jacks, DC power). Same coordinate format as `fixed_holes`. See [Enclosure presets](#enclosure-presets) below — presets include sensible default layouts for the top face that you can load in the drill editor.

### Merge behaviour

When a per-project `panel_config.json` is present, it is merged with the global defaults:

| Section | Behaviour |
|---------|-----------|
| `enclosure` | Project value replaces global entirely |
| `footprints` | Project entries add or override individual global entries; set a footprint to `null` to remove it; unmentioned footprints are inherited |
| `fixed_holes` | Project entries are appended after global entries |
| `remove_fixed_holes` | List of labels to remove from the global `fixed_holes` before appending project entries |

A common example: a two-footswitch design where the global centred footswitch entry needs to be replaced with two fixed holes at specific positions:

```json
{
  "remove_fixed_holes": ["Footswitch"],
  "fixed_holes": [
    {"label": "Footswitch L", "dia": 12.2, "x": -15, "y": -45.2},
    {"label": "Footswitch R", "dia": 12.2, "x":  15, "y": -45.2}
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

### Live enclosure preview

When `wx.html2` (the KiCad WebView component) is available, the main plugin dialog shows a live preview of the drilling template on the right-hand side. It renders automatically when the dialog opens, and refreshes whenever you close the drill editor or footprint rules editor.

Use the preview to catch common issues before generating the final PDF:

- **Wrong enclosure size** — if holes cluster near the top or bottom edge, or land outside the outline, the enclosure dimensions are likely off. Open **Edit Enclosure Drills…** and select the correct preset, or adjust Width/Height manually.
- **Missing holes** — if a panel-mounted control has no corresponding hole in the preview, its footprint type is not in the global rules. See [Footprint rules editor](#footprint-rules-editor) below.
- **Wrong hole position** — if a hole is present but in the wrong place, the `offset_x`/`offset_y` for that footprint needs adjustment. Open **Edit Enclosure Drills…**, select the footprint in the auto-detected holes list, and tweak the offsets; the preview updates as you type.

---

### Footprint rules editor

Click **Manage Autodetect Rules…** inside the **Edit Enclosure Drills** dialog to open the rules editor. It scans your board and compares every footprint that has a `Control` field against the global rules database.

**Top section — unrecognized footprints:** any footprint type found on the board that has no rule is listed here, with all the reference designators that use it and the `Control` label from the first one found. These are the footprints that would produce no hole in the drilling template.

To add a rule for a candidate:
1. Click it in the top list — the edit fields fill in with defaults (8 mm diameter, zero offsets, the `Control` value as the label).
2. Adjust the hole diameter and offsets as needed. The preview updates automatically so you can see where the hole lands relative to your other controls.
3. Click **Add as Global Rule ↓** — the footprint moves to the existing-rules list below and will appear in all future projects that use that footprint type.

**Bottom section — existing global rules:** shows every rule currently in the global database. Selecting a row lets you edit its settings live; the preview highlights that footprint's hole in red so you can verify the position.

#### Handling unrecognized footprints without adding a global rule

Not every missing footprint needs a permanent global rule. Two alternatives:

- **Fixed hole** — if the hole position is specific to this project (e.g. a second footswitch at a non-standard location), add it as a `fixed_holes` entry in the project's `panel_config.json` via **Edit Enclosure Drills…**. Fixed holes are placed by enclosure coordinates, not footprint position.
- **Null override** — if a footprint is in the global rules but you don't want a hole for it on this project, add it to the project `panel_config.json` `footprints` section with a value of `null`:

```json
{
  "footprints": {
    "Library:FootprintName": null
  }
}
```

---

### Enclosure presets

The plugin ships with built-in presets for common Hammond/Tayda enclosures. Selecting a preset fills in the enclosure dimensions and provides standard top-face (Side B) hole layouts for jacks and DC power.

| Preset | Width × Height (mm) | Notes |
|--------|----------------------|-------|
| `125B` | 62 × 119.5 | Most common stompbox size |
| `125B-R` | 119.5 × 62 | 125B rotated 90° (landscape on top) |
| `1590B` | 60 × 112 | Slightly smaller than 125B |
| `1590B-R` | 112 × 60 | |
| `1590BB` | 94 × 119.5 | Wider; good for multi-effect builds |
| `1590BB-R` | 119.5 × 94 | |
| `1590XX` | 121 × 145 | Large format |
| `1590XX-R` | 145 × 121 | |

To use a preset, open the **Edit Enclosure Drills** dialog (the pencil button next to the Enclosure Template checkbox) and select from the **Size** dropdown. The width, height, and depth fields will be filled in automatically.

#### Rotated (`-R`) presets

Rotated variants represent enclosures oriented with the long axis running left-to-right. The drilling template is rendered in landscape orientation to match, but the coordinates sent to Tayda are automatically converted to Tayda's portrait coordinate system (Tayda always publishes dimensions long-axis-vertical, labelled **Side C** for the left face).

#### Top face (Side B) hole layouts

Each non-rotated preset includes one or more named hole layouts for the top face — typically a standard "Input + Output + DC" arrangement. In the **Edit Enclosure Drills** dialog:

1. Select an enclosure preset from the **Size** dropdown.
2. The **Top face (Side B)** dropdown shows the available layouts for that preset.
3. Click **Apply Layout** to load the holes (you'll be asked to confirm, since this replaces any existing top-face holes).

The resulting holes appear in the read-only Side B list at the bottom of the dialog and are saved to your project's `panel_config.json` under the `side_b` key when you click **Apply**.

> **Note:** Top-face hole coordinates in the built-in presets are reasonable approximations based on the 125B as a reference. Verify against your specific enclosure before drilling — Tayda's published drawings are the authoritative source.

#### Snap lines

Enclosure presets can define **snap lines** — a grid of standard X and Y positions that hole coordinates are snapped to if they fall within a configurable radius. This corrects small PCB placement errors so holes land on the standard control spacing for that enclosure rather than being off by a fraction of a millimetre.

When snap is active, faint dashed blue guidelines appear on the drilling template preview at each snap position, making it easy to see whether your holes align with the expected layout.

The 125B preset ships with a default snap configuration. To customise snap for a different enclosure — or to override the 125B defaults for a specific project — add a `snap` block to the relevant `panel_config.json`:

```json
"snap": {
  "radius_mm": 0.75,
  "top_row_mm": 38,
  "x": [ -20.5, -16.5, 0, 16.5, 20.5 ],
  "y": [ -45.2, -25.4, -12.8, 12.6, 38 ]
}
```

- **`radius_mm`** — a hole within this distance of a snap line is moved to it. Set to `0` to disable snapping entirely.
- **`top_row_mm`** — Y position of the topmost control row in enclosure coordinates (mm above centre); used to anchor the overall vertical layout. Defaults to 38.
- **`x`** — list of X snap positions in mm from the enclosure centre (positive = right).
- **`y`** — list of Y snap positions in mm from the enclosure centre (positive = up).

To add snap to a preset rather than a project, add the same `snap` block directly to the enclosure's entry in `enclosure_presets.json` (in the plugin installation directory). This makes the snap lines available to all projects that use that preset, without requiring a per-project override.

X and Y axes are snapped independently — a hole near an X snap line only has its X corrected; Y is unchanged unless it also falls near a Y snap line.

---

#### Tayda drill manifest

If you use [Tayda Electronics](https://www.taydaelectronics.com) custom drilling, enable the **Tayda Drill Manifest** checkbox in the main dialog. This generates an additional PDF page — a table of Side / Diameter / X / Y suitable for pasting into Tayda's custom drill order form.

Coordinates are in mm from the centre of each face, rounded to one decimal place:
- **Side A** — front face (panel controls)
- **Side B** — top face (jacks, DC) — unrotated enclosures
- **Side C** — left face (jacks, DC) — rotated (`-R`) enclosures; Tayda's coordinate system for the jack side

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
