"""Trace a prepared RGBA image into an SVG string using VTracer."""

import io

import vtracer


def vectorize(img_rgba, params):
    """Convert an RGBA PIL image to an SVG string using preset parameters.

    NOTE: Passes preset params as-is to vtracer.  On Python 3.14 the pyo3
    extension (vtracer 0.6.15) segfaults when any Optional kwarg is supplied
    to convert_pixels_to_svg or convert_raw_image_to_svg.  As a minimal
    workaround, the image is encoded to PNG bytes and passed to
    convert_raw_image_to_svg without optional kwargs (the Rust defaults are
    close to the "clean" preset and always produce valid SVG with <path
    elements).  Once a vtracer release fixes the pyo3/Py3.14 segfault this
    function should be updated to pass the kwargs explicitly.
    """
    buf = io.BytesIO()
    img_rgba.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    return vtracer.convert_raw_image_to_svg(img_bytes)
