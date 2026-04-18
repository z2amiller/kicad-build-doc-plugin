from unittest.mock import MagicMock

from footprint_utils import friendly_footprint_type, get_field, ref_sort_key


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
