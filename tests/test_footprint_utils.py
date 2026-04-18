from unittest.mock import MagicMock

from footprint_utils import extract_controls, friendly_footprint_type, get_field, ref_sort_key


def test_ref_sort_key_numeric_order():
    assert ref_sort_key("R10") > ref_sort_key("R9")


def test_ref_sort_key_prefix_order():
    assert ref_sort_key("C1") < ref_sort_key("R1")


def test_ref_sort_key_no_number():
    assert ref_sort_key("U") == ("U", 0)


def test_ref_sort_key_mixed_case():
    assert ref_sort_key("rv1") == ("RV", 1)


def test_friendly_type_resistor():
    assert friendly_footprint_type("R1", "") == "Resistor, 1/4W"


def test_friendly_type_capacitor():
    assert friendly_footprint_type("C10", "") == "Capacitor"


def test_friendly_type_pot():
    assert friendly_footprint_type("RV2", "") == "Potentiometer"


def test_friendly_type_unknown_uses_fp_name():
    assert friendly_footprint_type("XY1", "MyFootprint") == "MyFootprint"


def test_friendly_type_unknown_no_fp_name():
    assert friendly_footprint_type("XY1", "") == "Component"


def _make_field(name, value):
    """Build a kipy-style Field mock."""
    f = MagicMock()
    f.name = name
    f.text.value = value
    return f


def test_get_field_found():
    fp = MagicMock()
    fp.texts_and_fields = [_make_field("Control", "  Volume  ")]
    assert get_field(fp, "Control") == "Volume"


def test_get_field_found_case_insensitive():
    fp = MagicMock()
    fp.texts_and_fields = [_make_field("control", "Level")]
    assert get_field(fp, "Control") == "Level"


def test_get_field_missing():
    fp = MagicMock()
    fp.texts_and_fields = []
    assert get_field(fp, "Control") == ""


def test_get_field_wrong_name():
    fp = MagicMock()
    fp.texts_and_fields = [_make_field("Datasheet", "http://example.com")]
    assert get_field(fp, "Control") == ""


def test_get_field_non_field_item_skipped():
    # BoardText items (no .name attribute) should be silently skipped.
    item = MagicMock(spec=[])  # spec=[] → no attributes → getattr returns None
    fp = MagicMock()
    fp.texts_and_fields = [item]
    assert get_field(fp, "Control") == ""


# ── extract_controls ──────────────────────────────────────────────────────────

def _make_fp_with_control(ref, value, control, fp_id="Lib:Part"):
    fp = MagicMock()
    fp.reference_field.text.value = ref
    fp.value_field.text.value = value
    lib, name = fp_id.split(":")
    fp.definition.id.library = lib
    fp.definition.id.name = name
    field = MagicMock()
    field.name = "Control"
    field.text.value = control
    fp.texts_and_fields = [field]
    return fp


def _make_board_ec(fps):
    board = MagicMock()
    board.get_footprints.return_value = fps
    return board


def test_extract_controls_empty_board():
    result = extract_controls(_make_board_ec([]), set())
    assert result == {"external": [], "internal": []}


def test_extract_controls_no_control_field():
    fp = MagicMock()
    fp.reference_field.text.value = "R1"
    fp.texts_and_fields = []
    result = extract_controls(_make_board_ec([fp]), set())
    assert result == {"external": [], "internal": []}


def test_extract_controls_external_vs_internal():
    ext_fp = _make_fp_with_control("RV1", "B100K", "Volume", "Panel:Alpha9mm")
    int_fp = _make_fp_with_control("RV2", "B10K",  "Tone",   "Lib:Trim")
    external_ids = {"Panel:Alpha9mm"}
    result = extract_controls(_make_board_ec([ext_fp, int_fp]), external_ids)
    assert len(result["external"]) == 1
    assert result["external"][0]["label"] == "Volume"
    assert len(result["internal"]) == 1
    assert result["internal"][0]["label"] == "Tone"


def test_extract_controls_deduplicates_labels():
    fps = [
        _make_fp_with_control("RV1", "B100K", "Volume"),
        _make_fp_with_control("RV2", "B100K", "Volume"),  # duplicate label
    ]
    result = extract_controls(_make_board_ec(fps), set())
    assert len(result["internal"]) == 1


def test_extract_controls_excludes_leds_and_diodes():
    fps = [
        _make_fp_with_control("D1",   "1N4148", "Clip"),
        _make_fp_with_control("LED1", "Red",    "Indicator"),
    ]
    result = extract_controls(_make_board_ec(fps), set())
    assert result == {"external": [], "internal": []}


def test_extract_controls_sorted_by_ref():
    fps = [
        _make_fp_with_control("RV10", "B100K", "Reverb"),
        _make_fp_with_control("RV2",  "B100K", "Delay"),
        _make_fp_with_control("RV1",  "B100K", "Volume"),
    ]
    result = extract_controls(_make_board_ec(fps), set())
    labels = [c["label"] for c in result["internal"]]
    assert labels == ["Volume", "Delay", "Reverb"]
