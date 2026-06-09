"""Deterministic auto-tuning critic loop: trace, render, score, keep the best.

Requires the optional `[auto]` extra (resvg-py, scikit-image, numpy). Import
this module only when --auto is requested; the base install does not ship
these dependencies.
"""

import io

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from .preprocess import quantize
from .vectorize import vectorize


def render_svg(svg, size):
    """Render an SVG string to an RGB PIL image of the given (width, height).

    Uses resvg (spec-accurate, self-contained); falls back to cairosvg.
    Transparent areas are flattened onto white so scoring is consistent.
    """
    try:
        import resvg_py

        png = bytes(resvg_py.svg_to_bytes(svg_string=svg, background="white"))
    except ImportError:
        import cairosvg

        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), background_color="white")

    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.size != size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return img


def score(candidate_rgb, source_rgb):
    """Color-aware SSIM between two equal-size RGB images. Higher is closer.

    Returns a float in roughly [-1, 1]; 1.0 means identical.
    """
    a = np.asarray(candidate_rgb, dtype=np.float64)
    b = np.asarray(source_rgb, dtype=np.float64)
    return float(structural_similarity(a, b, channel_axis=2, data_range=255.0))
