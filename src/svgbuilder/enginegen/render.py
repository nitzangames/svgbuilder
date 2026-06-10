"""Render an SVG string to PNG bytes (for the critique loop and previews)."""


def render_png_bytes(svg):
    """Rasterize an SVG string to PNG bytes on a white background, via resvg."""
    import resvg_py

    return bytes(resvg_py.svg_to_bytes(svg_string=svg, background="white"))
