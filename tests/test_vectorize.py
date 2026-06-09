from PIL import Image
from svgbuilder.presets import get_preset
from svgbuilder.vectorize import vectorize


def _two_color_image():
    img = Image.new("RGBA", (32, 32), (0, 128, 0, 255))
    for y in range(32):
        for x in range(16):
            img.putpixel((x, y), (200, 30, 30, 255))
    return img


def test_vectorize_returns_svg_with_paths():
    svg = vectorize(_two_color_image(), get_preset("clean"))
    assert isinstance(svg, str)
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    assert "<path" in svg
