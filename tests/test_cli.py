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
