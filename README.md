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

- **External** — controls that appear on the enclosure panel (pots, jacks, footswitches, toggle switches). These are footprints listed in `external_footprints.txt` (see below).
- **Internal** — controls accessible inside the enclosure (trimmers, DIP switches, internal jumpers).

A few component types are automatically excluded from the **internal** list even if they have a `Control` field: test points (`TP*`), LEDs and diodes (`LED*`, `D*`), and single-pad footprints. These are indicators or debug aids, not controls a builder needs to set.

---

## Enclosure drilling template

The plugin can generate a 1:1 scale drilling template for your enclosure — print it, tape it to the enclosure, and use it to mark hole positions before drilling.

Hole positions are determined by the footprint positions on the board, transformed into enclosure coordinates. The plugin needs to know which footprints correspond to panel-mounted components and what hole size each requires. This is configured in a plain-text file called **`external_footprints.txt`**.

### The `external_footprints.txt` file

The plugin ships with a default `external_footprints.txt` covering common footprints. You can override it per-project by placing a file with the same name in your project directory (next to the `.kicad_pcb` file) — the project-level file takes precedence.

#### File format

Lines starting with `#` are comments. There are three types of entries:

**Enclosure dimensions:**
```
ENCLOSURE  width_mm  height_mm  [depth_mm]
```
Sets the physical size of the enclosure face. `depth_mm` defaults to 35 if omitted.

```
ENCLOSURE 62 117 35
```

**Autodetection: Panel footprints** (external controls that need drilled holes):
```
LibraryName:FootprintName  hole_dia_mm  offset_x_mm  offset_y_mm  [label]
```

- `LibraryName:FootprintName` — the full KiCad footprint ID as it appears in the board (e.g. `_MB_switches:SPDT.LUGS`)
- `hole_dia_mm` — the drill diameter in millimetres
- `offset_x_mm`, `offset_y_mm` — shift the hole position relative to the footprint's origin on the PCB (use this when the physical hole should not be centred on the footprint origin)
- `label` — optional; if omitted, the footprint's `Control` field is used, then the reference

```
_MB_switches:SPDT.LUGS           7.6   0    0
_MB_potentiometers:16MM_B.MOUNT  8.2   0    16
Panel:Alpha9mm                   7.0   0    0       Volume
LED_THT:LED_D3.0mm               3.2   1.27 0       LED
```

**Fixed holes** (holes at specific enclosure coordinates, not derived from PCB position):
```
FIXED  label  hole_dia_mm  x_mm  y_mm
```

Coordinates are in mm measured from the enclosure centre. Positive Y is up, positive X is right.

```
FIXED  Footswitch  12.2   0      -45.2
FIXED  LED          3.2  -20.5   -45.2    
```

### How hole positions are calculated

Footprint positions are read from the PCB in millimetres. The plugin:

1. Mirrors the X axis (the panel is viewed from outside, which is the opposite of looking at the PCB front)
2. Anchors the Y axis so the topmost external control row lands 38 mm above the enclosure centre — a reasonable default for most stompbox layouts

The `offset_x` and `offset_y` values in `external_footprints.txt` are applied **after** this coordinate transform. Use them when a component's mounting hole is not at its KiCad footprint origin — for example, an Alpha pot where the mechanical hole is offset from the electrical origin, or an LED whose hole is beside the component body.

### Per-project overrides

Place an `external_footprints.txt` file in the same directory as your `.kicad_pcb` file. It completely replaces the plugin default for that project.

**Common reasons to add a per-project override:**

- Your enclosure is a non-standard size
- You need fixed holes for a DC jack or footswitch at a specific position (e.g. double footswitches)
- A custom footprint has different hole sizing than the default
- You want to override only the enclosure dimensions and keep the footprint list as-is

Example per-project `external_footprints.txt`:

```
# Tayda 1590B-style enclosure
ENCLOSURE 112 60 31

# Standard panel footprints
_MB_switches:SPDT.LUGS  7.6  0  0
Panel:Alpha9mm           7.0  0  0

# Fixed holes — bypass footswitch is at a fixed panel position
FIXED  Bypass  12.2  0  -22
```

### Autodetection: Back-panel LEDs

LEDs mounted on the **back copper layer** (B.Cu) are treated as panel indicators and automatically get a hole in the drilling template — no entry in `external_footprints.txt` required. The default hole diameter is 3.2 mm. To override the size for a specific LED footprint, add it to `external_footprints.txt` as a normal footprint entry.

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
