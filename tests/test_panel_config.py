import textwrap

from panel_config import load_panel_config


def test_enclosure_parsed(tmp_path):
    (tmp_path / "external_footprints.txt").write_text(
        textwrap.dedent("""\
            ENCLOSURE 62 117 35
            FIXED Footswitch 12.2 0 -45.2
            _MB_switches:SPDT.LUGS 7.6 0 0
        """)
    )
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result["enclosure"]["width"] == 62
    assert result["enclosure"]["height"] == 117
    assert result["enclosure"]["depth"] == 35
    assert len(result["fixed_holes"]) == 1
    assert result["fixed_holes"][0]["label"] == "Footswitch"
    assert result["fixed_holes"][0]["dia"] == 12.2
    assert "_MB_switches:SPDT.LUGS" in result["footprints"]


def test_footprint_with_label(tmp_path):
    (tmp_path / "external_footprints.txt").write_text("LED_THT:LED_D3.0mm 3.2 1.27 0 LED\n")
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    fp = result["footprints"]["LED_THT:LED_D3.0mm"]
    assert fp["hole_dia"] == 3.2
    assert fp["offset_x"] == 1.27
    assert fp["label"] == "LED"


def test_footprint_without_label(tmp_path):
    (tmp_path / "external_footprints.txt").write_text("_MB_switches:SPDT.LUGS 7.6 0 0\n")
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    fp = result["footprints"]["_MB_switches:SPDT.LUGS"]
    assert fp["label"] is None


def test_comments_ignored(tmp_path):
    (tmp_path / "external_footprints.txt").write_text(
        "# comment\nENCLOSURE 50 100  # inline comment\n"
    )
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result["enclosure"]["width"] == 50


def test_project_dir_takes_precedence(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (plugin_dir / "external_footprints.txt").write_text("ENCLOSURE 50 100\n")
    (project_dir / "external_footprints.txt").write_text("ENCLOSURE 62 117\n")
    result = load_panel_config(str(project_dir / "board.kicad_pcb"), str(plugin_dir))
    assert result["enclosure"]["width"] == 62


def test_default_enclosure_when_no_config(tmp_path):
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    assert result["enclosure"]["width"] == 62
    assert result["enclosure"]["height"] == 117
    assert result["footprints"] == {}
    assert result["fixed_holes"] == []


def test_fixed_hole_fields(tmp_path):
    (tmp_path / "external_footprints.txt").write_text("FIXED FS 12.2 0.0 -45.2\n")
    result = load_panel_config(str(tmp_path / "board.kicad_pcb"), str(tmp_path))
    hole = result["fixed_holes"][0]
    assert hole["label"] == "FS"
    assert hole["dia"] == 12.2
    assert hole["x"] == 0.0
    assert hole["y"] == -45.2
