from PIL import Image
from svgbuilder.cli import derive_output_path, build_params, main


def test_derive_output_path_defaults_next_to_input():
    assert derive_output_path("/a/b/train.jpg", None) == "/a/b/train.svg"


def test_derive_output_path_respects_explicit():
    assert derive_output_path("/a/b/train.jpg", "/out/x.svg") == "/out/x.svg"


def test_build_params_applies_preset_then_overrides():
    p = build_params(preset="clean", colors=None)
    assert p["colors"] == 16
    p2 = build_params(preset="clean", colors=5)
    assert p2["colors"] == 5  # explicit flag overrides preset


def test_main_end_to_end_writes_valid_svg(tmp_path):
    src = tmp_path / "in.png"
    img = Image.new("RGBA", (24, 24), (0, 128, 0, 255))
    for x in range(12):
        for y in range(24):
            img.putpixel((x, y), (200, 30, 30, 255))
    img.save(src)
    out = tmp_path / "out.svg"

    exit_code = main([str(src), "-o", str(out), "--quiet"])

    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text


def test_main_missing_file_returns_nonzero(tmp_path):
    exit_code = main([str(tmp_path / "nope.png"), "--quiet"])
    assert exit_code == 2  # missing input has its own exit code, distinct from 1


def _wide_fixture(tmp_path):
    src = tmp_path / "big.png"
    img = Image.new("RGBA", (900, 300), (0, 128, 0, 255))
    for x in range(450):
        for y in range(300):
            img.putpixel((x, y), (200, 30, 30, 255))
    img.save(src)
    return src


def _svg_width(text):
    import re
    return int(re.search(r'width="(\d+)"', text).group(1))


def test_preset_max_size_downscales(tmp_path):
    # 'simple' carries max_size=450, so a 900px-wide input is downscaled.
    src = _wide_fixture(tmp_path)
    out = tmp_path / "o.svg"
    assert main([str(src), "-o", str(out), "--preset", "simple", "--quiet"]) == 0
    assert _svg_width(out.read_text()) <= 450


def test_max_size_flag_overrides_preset(tmp_path):
    src = _wide_fixture(tmp_path)
    out = tmp_path / "o.svg"
    assert main([str(src), "-o", str(out), "--preset", "simple",
                 "--max-size", "200", "--quiet"]) == 0
    assert _svg_width(out.read_text()) <= 200


def test_main_auto_flag_writes_svg(tmp_path):
    out = tmp_path / "auto.svg"
    exit_code = main([
        "tests/fixtures/sample.png", "-o", str(out),
        "--auto", "--auto-budget", "3", "--no-smooth", "--quiet",
    ])
    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text


def test_main_llm_refine_falls_back_when_suggester_unavailable(tmp_path, monkeypatch, capsys):
    # Force the LLM path to fail deterministically (no network): make_suggester
    # raises, simulating a missing key / unavailable API. The CLI must catch it,
    # print a fallback warning, run the deterministic loop, and still write SVG.
    import svgbuilder.llm_refine as llm_refine

    def boom(*args, **kwargs):
        raise RuntimeError("no api key")

    monkeypatch.setattr(llm_refine, "make_suggester", boom)

    out = tmp_path / "llm.svg"
    exit_code = main([
        "tests/fixtures/sample.png", "-o", str(out),
        "--llm-refine", "--auto-budget", "3", "--no-smooth",
    ])
    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text
    err = capsys.readouterr().err
    assert "fall" in err.lower() or "deterministic" in err.lower()
