from PIL import Image
from svgbuilder.preprocess import load_image, quantize


def _gradient(w, h):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    return img.convert("RGBA")


def test_load_downscales_to_max_size(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (2000, 1000)).save(src)
    img = load_image(str(src), max_size=500, bg="auto")
    assert max(img.size) == 500
    assert img.mode == "RGBA"


def test_load_keeps_small_image_unchanged(tmp_path):
    src = tmp_path / "small.png"
    Image.new("RGB", (100, 80)).save(src)
    img = load_image(str(src), max_size=500, bg="auto")
    assert img.size == (100, 80)


def test_load_white_bg_flattens_alpha(tmp_path):
    src = tmp_path / "alpha.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(src)
    img = load_image(str(src), max_size=500, bg="white")
    assert img.getpixel((0, 0)) == (255, 255, 255, 255)


def test_quantize_reduces_distinct_colors():
    img = _gradient(64, 64)
    q = quantize(img, colors=8, smooth=False)
    distinct = {p for p in q.getdata()}
    assert len(distinct) <= 8
    assert q.mode == "RGBA"
