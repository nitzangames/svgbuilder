import pytest
from svgbuilder.presets import get_preset, PRESET_NAMES


def test_clean_is_default_with_16_colors():
    p = get_preset("clean")
    assert p["colors"] == 16
    assert p["mode"] == "spline"
    assert p["color_precision"] == 4


def test_flat_is_8_colors():
    assert get_preset("flat")["colors"] == 8


def test_detailed_is_24_colors():
    assert get_preset("detailed")["colors"] == 24


def test_returns_a_copy_not_shared_state():
    a = get_preset("clean")
    a["colors"] = 999
    assert get_preset("clean")["colors"] == 16


def test_unknown_preset_raises_valueerror():
    with pytest.raises(ValueError):
        get_preset("nope")


def test_preset_names_listed():
    assert set(PRESET_NAMES) == {"flat", "clean", "detailed"}
