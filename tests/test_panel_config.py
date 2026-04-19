import json

from panel_config import (
    ENCLOSURE_PRESETS,
    _SIDE_B_DEFAULTS,
    load_blurb,
    load_copyright,
    load_panel_config,
    load_text_file,
)



# ── load_panel_config (JSON) ──────────────────────────────────────────────────

def _write_config(path, data):
    path.write_text(json.dumps(data))


def test_enclosure_parsed(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117, "depth": 35},
        "fixed_holes": [{"label": "Footswitch", "dia": 12.2, "x": 0, "y": -45.2}],
        "footprints": {"_MB_switches:SPDT.LUGS": {"hole_dia": 7.6, "offset_x": 0, "offset_y": 0}},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.width == 62
    assert result.enclosure.height == 117
    assert result.enclosure.depth == 35


def test_fixed_hole_fields(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "fixed_holes": [{"label": "FS", "dia": 12.2, "x": 0.0, "y": -45.2}],
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    hole = result.fixed_holes[0]
    assert hole.label == "FS"
    assert hole.dia == 12.2
    assert hole.x == 0.0
    assert hole.y == -45.2


def test_footprint_parsed(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "footprints": {
            "Panel:Alpha9mm": {"hole_dia": 7.0, "offset_x": 1.0, "offset_y": 2.0, "label": "Volume"},
        },
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    fp = result.footprints["Panel:Alpha9mm"]
    assert fp.hole_dia == 7.0
    assert fp.offset_x == 1.0
    assert fp.offset_y == 2.0
    assert fp.label == "Volume"


def test_footprint_use_pad_centroid_parsed(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "footprints": {
            "LED_THT:LED_D3.0mm": {"hole_dia": 3.2, "offset_x": 0, "offset_y": 0, "use_pad_centroid": True},
        },
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.footprints["LED_THT:LED_D3.0mm"].use_pad_centroid is True


def test_footprint_use_pad_centroid_defaults_false(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "footprints": {"Lib:Part": {"hole_dia": 7.6, "offset_x": 0, "offset_y": 0}},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.footprints["Lib:Part"].use_pad_centroid is False


# ── Enclosure presets ─────────────────────────────────────────────────────────

def test_preset_table_has_expected_sizes():
    assert "125B" in ENCLOSURE_PRESETS
    assert "1590B" in ENCLOSURE_PRESETS
    assert "1590BB" in ENCLOSURE_PRESETS
    assert "1590A" in ENCLOSURE_PRESETS
    assert "1590XX" in ENCLOSURE_PRESETS


def test_rotated_presets_swap_width_height():
    for name, (w, h, d) in ENCLOSURE_PRESETS.items():
        if name.endswith("-R"):
            base = name[:-2]
            assert base in ENCLOSURE_PRESETS
            bw, bh, bd = ENCLOSURE_PRESETS[base]
            assert w == bh and h == bw and d == bd


def test_rotated_preset_sets_rotated_flag(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "1590XX-R"},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.rotated is True
    assert result.enclosure.width == 145.0
    assert result.enclosure.height == 121.0


def test_non_rotated_preset_rotated_flag_false(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "1590XX"},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.rotated is False


def test_custom_enclosure_rotated_flag_false(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 80, "height": 120},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.rotated is False


def test_preset_resolves_dimensions(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "1590B"},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    w, h, d = ENCLOSURE_PRESETS["1590B"]
    assert result.enclosure.width == w
    assert result.enclosure.height == h
    assert result.enclosure.depth == d
    assert result.enclosure.preset == "1590B"


def test_preset_allows_dimension_override(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "125B", "depth": 40.0},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    w, h, _ = ENCLOSURE_PRESETS["125B"]
    assert result.enclosure.width == w
    assert result.enclosure.height == h
    assert result.enclosure.depth == 40.0


def test_unknown_preset_falls_back_to_explicit_dimensions(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "CUSTOM_BOX", "width": 55.0, "height": 100.0},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.width == 55.0
    assert result.enclosure.height == 100.0
    assert result.enclosure.preset is None


def test_no_preset_key_uses_explicit_dimensions(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117, "depth": 35},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.preset is None
    assert result.enclosure.width == 62


def test_footprint_label_optional(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "footprints": {"Lib:Part": {"hole_dia": 7.6, "offset_x": 0, "offset_y": 0}},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.footprints["Lib:Part"].label is None


def test_depth_defaults_to_35(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.depth == 35.0


def test_missing_config_uses_defaults(tmp_path):
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.enclosure.width == 62
    assert result.enclosure.height == 117
    assert result.footprints == {}
    assert result.fixed_holes == []


# ── merge behaviour ───────────────────────────────────────────────────────────

def test_merge_enclosure_overridden(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117, "depth": 35},
        "footprints": {"Lib:A": {"hole_dia": 7.6, "offset_x": 0, "offset_y": 0}},
    })
    _write_config(project_dir / "panel_config.json", {
        "enclosure": {"width": 112, "height": 60, "depth": 31},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert result.enclosure.width == 112
    assert result.enclosure.depth == 31
    # global footprint still inherited
    assert "Lib:A" in result.footprints


def test_merge_footprints_additive(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "footprints": {"Lib:A": {"hole_dia": 7.0, "offset_x": 0, "offset_y": 0}},
    })
    _write_config(project_dir / "panel_config.json", {
        "footprints": {"Lib:B": {"hole_dia": 8.0, "offset_x": 0, "offset_y": 0}},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert "Lib:A" in result.footprints
    assert "Lib:B" in result.footprints


def test_merge_footprint_override(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "footprints": {"Lib:A": {"hole_dia": 7.0, "offset_x": 0, "offset_y": 0}},
    })
    _write_config(project_dir / "panel_config.json", {
        "footprints": {"Lib:A": {"hole_dia": 9.0, "offset_x": 0, "offset_y": 0}},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert result.footprints["Lib:A"].hole_dia == 9.0


def test_merge_footprint_null_removes(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "footprints": {"Lib:A": {"hole_dia": 7.6, "offset_x": 0, "offset_y": 0}},
    })
    _write_config(project_dir / "panel_config.json", {
        "footprints": {"Lib:A": None},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert "Lib:A" not in result.footprints


def test_merge_fixed_holes_replaces_when_present(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "fixed_holes": [{"label": "Global", "dia": 12.2, "x": 0, "y": 0}],
    })
    _write_config(project_dir / "panel_config.json", {
        "fixed_holes": [{"label": "Project", "dia": 8.0, "x": 10, "y": 10}],
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    labels = [h.label for h in result.fixed_holes]
    assert labels == ["Project"]
    assert "Global" not in labels


def test_merge_fixed_holes_inherited_when_absent(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "fixed_holes": [{"label": "Global", "dia": 12.2, "x": 0, "y": 0}],
    })
    _write_config(project_dir / "panel_config.json", {
        "enclosure": {"width": 112, "height": 60},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    labels = [h.label for h in result.fixed_holes]
    assert labels == ["Global"]


def test_merge_two_footswitches(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "fixed_holes": [{"label": "Footswitch", "dia": 12.2, "x": 0, "y": -45.2}],
    })
    _write_config(project_dir / "panel_config.json", {
        "fixed_holes": [
            {"label": "Footswitch L", "dia": 12.2, "x": -15, "y": -45.2},
            {"label": "Footswitch R", "dia": 12.2, "x":  15, "y": -45.2},
        ],
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    labels = [h.label for h in result.fixed_holes]
    assert "Footswitch" not in labels
    assert "Footswitch L" in labels
    assert "Footswitch R" in labels


# ── load_text_file / load_copyright / load_blurb ──────────────────────────────

def test_load_text_file_found(tmp_path):
    (tmp_path / "foo.txt").write_text("hello\nworld\n")
    assert load_text_file("foo.txt", [str(tmp_path)]) == "hello\nworld"


def test_load_text_file_missing(tmp_path):
    assert load_text_file("nope.txt", [str(tmp_path)]) is None


def test_load_text_file_first_dir_wins(tmp_path):
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir(); d2.mkdir()
    (d1 / "f.txt").write_text("from-a")
    (d2 / "f.txt").write_text("from-b")
    assert load_text_file("f.txt", [str(d1), str(d2)]) == "from-a"


def test_load_copyright_present(tmp_path):
    (tmp_path / "copyright.txt").write_text("© 2025 Me")
    assert load_copyright(str(tmp_path)) == "© 2025 Me"


def test_load_copyright_absent(tmp_path):
    assert load_copyright(str(tmp_path)) is None


def test_load_blurb_present(tmp_path):
    (tmp_path / "builddoc_blurb.txt").write_text("A short description.\n")
    assert load_blurb(str(tmp_path)) == "A short description."


def test_load_blurb_absent(tmp_path):
    assert load_blurb(str(tmp_path)) is None


# ── Side B ────────────────────────────────────────────────────────────────────

def test_side_b_explicit_holes_parsed(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117},
        "side_b": [
            {"label": "Input",  "diameter_mm": 9.53, "x_mm": -15.0, "y_mm": 0.0},
            {"label": "Output", "diameter_mm": 9.53, "x_mm":  15.0, "y_mm": 0.0},
        ],
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert len(result.side_b) == 2
    assert result.side_b[0].label == "Input"
    assert result.side_b[0].diameter_mm == 9.53
    assert result.side_b[0].x_mm == -15.0
    assert result.side_b[1].label == "Output"


def test_side_b_preset_provides_defaults(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "125B"},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert len(result.side_b) == len(_SIDE_B_DEFAULTS["125B"])
    labels = [h.label for h in result.side_b]
    assert "Input" in labels
    assert "Output" in labels
    assert "DC" in labels


def test_side_b_empty_when_no_preset_and_no_explicit(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result.side_b == []


def test_side_b_explicit_overrides_preset_defaults(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "125B"},
        "side_b": [{"label": "Custom", "diameter_mm": 8.0, "x_mm": 0.0, "y_mm": 0.0}],
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert len(result.side_b) == 1
    assert result.side_b[0].label == "Custom"


def test_side_b_merge_project_replaces_global(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "side_b": [{"label": "Global DC", "diameter_mm": 12.0, "x_mm": 0.0, "y_mm": 0.0}],
    })
    _write_config(project_dir / "panel_config.json", {
        "side_b": [{"label": "Project DC", "diameter_mm": 12.0, "x_mm": 5.0, "y_mm": 0.0}],
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert len(result.side_b) == 1
    assert result.side_b[0].label == "Project DC"


def test_side_b_merge_inherits_global_when_absent(tmp_path):
    plugin_dir = tmp_path / "plugin"
    project_dir = tmp_path / "project"
    plugin_dir.mkdir(); project_dir.mkdir()
    _write_config(plugin_dir / "panel_config.json", {
        "side_b": [{"label": "Global DC", "diameter_mm": 12.0, "x_mm": 0.0, "y_mm": 0.0}],
    })
    _write_config(project_dir / "panel_config.json", {
        "enclosure": {"width": 62, "height": 117},
    })
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert len(result.side_b) == 1
    assert result.side_b[0].label == "Global DC"


def test_side_b_1590a_has_no_dc(tmp_path):
    _write_config(tmp_path / "panel_config.json", {
        "enclosure": {"preset": "1590A"},
    })
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    labels = [h.label for h in result.side_b]
    assert "DC" not in labels
    assert "Input" in labels
    assert "Output" in labels
