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


# Candidate values explored per knob during coordinate descent.
_SEARCH = {
    "color_precision": [3, 4, 5, 6],
    "filter_speckle": [2, 4, 6, 8, 10],
    "corner_threshold": [40, 50, 60, 70],
}


def _flatten(img_rgba):
    """Composite an RGBA image onto white and return RGB (for scoring)."""
    bg = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img_rgba).convert("RGB")


def _trace_and_score(source_rgba, source_rgb, params, smooth):
    """Quantize + trace with `params`, render, and score against the source."""
    img_q = quantize(source_rgba, colors=params["colors"], smooth=smooth)
    svg = vectorize(img_q, params)
    rendered = render_svg(svg, source_rgba.size)
    return svg, score(rendered, source_rgb)


def auto_vectorize(source_rgba, base_params, smooth=True, budget=6):
    """Search the tracing parameters by coordinate descent, keep the best.

    Renders and SSIM-scores each candidate against `source_rgba`. Starts from
    `base_params`, tries neighbour values for each knob, and accepts a change
    only when it strictly improves the score. Always returns the best result
    seen (never worse than the baseline single trace). Stops at `budget`
    evaluations or when a full pass yields no improvement.

    Returns (best_svg, best_params, best_score, evals).
    """
    source_rgb = _flatten(source_rgba)
    params = dict(base_params)

    best_svg, best_score = _trace_and_score(source_rgba, source_rgb, params, smooth)
    evals = 1

    improved = True
    while improved and evals < budget:
        improved = False
        for knob, values in _SEARCH.items():
            for value in values:
                if evals >= budget:
                    break
                if params.get(knob) == value:
                    continue
                candidate = dict(params)
                candidate[knob] = value
                svg, candidate_score = _trace_and_score(
                    source_rgba, source_rgb, candidate, smooth
                )
                evals += 1
                if candidate_score > best_score:
                    best_score, best_svg, params = candidate_score, svg, candidate
                    improved = True

    return best_svg, params, best_score, evals
