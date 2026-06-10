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


from svgbuilder.llm_refine import llm_refine_vectorize
from svgbuilder.preprocess import load_image

_FIXTURE = "tests/fixtures/sample.png"


def test_llm_refine_returns_svg_and_respects_budget():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    calls = {"n": 0}

    def suggest(source_rgb, candidate_rgb, current_params):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"done": False, "filter_speckle": 8}
        return {"done": True}

    svg, params, best, evals = llm_refine_vectorize(
        src, get_preset("clean"), smooth=False, budget=5, suggest=suggest
    )
    assert "<path" in svg
    assert 1 <= evals <= 5
    assert -1.0 <= best <= 1.0
    assert isinstance(params, dict)


def test_llm_refine_stops_on_done():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    def suggest(source_rgb, candidate_rgb, current_params):
        return {"done": True}

    svg, params, best, evals = llm_refine_vectorize(
        src, get_preset("clean"), smooth=False, budget=5, suggest=suggest
    )
    assert evals == 1  # baseline only; suggester immediately said done


def test_llm_refine_propagates_first_call_error():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    def suggest(source_rgb, candidate_rgb, current_params):
        raise RuntimeError("no api key")

    import pytest
    with pytest.raises(RuntimeError):
        llm_refine_vectorize(src, get_preset("clean"), smooth=False, budget=5, suggest=suggest)


def test_llm_refine_never_worse_than_baseline():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")
    base = get_preset("clean")

    from svgbuilder.autotune import render_svg, score
    from svgbuilder.preprocess import quantize
    from svgbuilder.vectorize import vectorize
    src_rgb = src.convert("RGB")
    base_svg = vectorize(quantize(src, colors=base["colors"], smooth=False), base)
    base_score = score(render_svg(base_svg, src.size), src_rgb)

    def suggest(source_rgb, candidate_rgb, current_params):
        # propose a likely-worse extreme, then stop
        return {"done": True} if current_params.get("color_precision") == 2 else {"color_precision": 2}

    _svg, _params, best, _evals = llm_refine_vectorize(
        src, base, smooth=False, budget=4, suggest=suggest
    )
    assert best >= base_score - 1e-9
