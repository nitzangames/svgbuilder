"""Trace a prepared RGBA image into an SVG string using VTracer."""

import vtracer


def vectorize(img_rgba, params):
    """Convert an RGBA PIL image to an SVG string using preset parameters.

    Requires Python 3.10-3.13. The vtracer 0.6.15 cp314 wheel has a pyo3 bug
    that segfaults whenever a tuning parameter is passed, so Python 3.14 is
    not supported (see pyproject.toml requires-python and the README).
    """
    pixels = list(img_rgba.getdata())
    return vtracer.convert_pixels_to_svg(
        pixels,
        size=img_rgba.size,
        colormode="color",
        hierarchical="stacked",
        mode=params["mode"],
        filter_speckle=params["filter_speckle"],
        color_precision=params["color_precision"],
        layer_difference=params["layer_difference"],
        corner_threshold=params["corner_threshold"],
        length_threshold=params["length_threshold"],
        max_iterations=10,
        splice_threshold=params["splice_threshold"],
        path_precision=8,
    )
