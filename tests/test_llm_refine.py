from svgbuilder.llm_refine import apply_suggestion
from svgbuilder.presets import get_preset


def test_apply_suggestion_applies_valid_values():
    base = get_preset("clean")
    out = apply_suggestion(base, {"color_precision": 3, "mode": "polygon"})
    assert out["color_precision"] == 3
    assert out["mode"] == "polygon"


def test_apply_suggestion_ignores_out_of_range_and_unknown_keys():
    base = get_preset("clean")
    out = apply_suggestion(base, {"color_precision": 999, "colors": 4, "bogus": 1})
    assert out["color_precision"] == base["color_precision"]  # 999 not allowed
    assert out["colors"] == base["colors"]                    # colors not tunable here
    assert "bogus" not in out


def test_apply_suggestion_returns_a_copy():
    base = get_preset("clean")
    out = apply_suggestion(base, {"filter_speckle": 8})
    out["filter_speckle"] = -1
    assert get_preset("clean")["filter_speckle"] == base["filter_speckle"]
    assert base["filter_speckle"] != -1


def test_apply_suggestion_ignores_done_and_non_param_fields():
    base = get_preset("clean")
    out = apply_suggestion(base, {"done": True, "corner_threshold": 40})
    assert "done" not in out
    assert out["corner_threshold"] == 40
