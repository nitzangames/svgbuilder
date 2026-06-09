"""Load and prepare a raster image for tracing."""

from PIL import Image, ImageFilter


def load_image(path, max_size=1000, bg="auto"):
    """Open an image as RGBA, optionally flatten background, and downscale.

    bg: "white" flattens transparency onto white; "none"/"auto" preserve alpha.
    max_size: longest-edge cap in pixels; larger images are downscaled.
    """
    img = Image.open(path).convert("RGBA")

    if bg == "white":
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)

    longest = max(img.size)
    if longest > max_size:
        scale = max_size / longest
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    return img


def quantize(img, colors=16, smooth=True):
    """Reduce the image to a fixed palette (deterministic, no dithering)."""
    if smooth:
        img = img.filter(ImageFilter.MedianFilter(size=3))
    q = img.quantize(
        colors=colors,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    )
    return q.convert("RGBA")
