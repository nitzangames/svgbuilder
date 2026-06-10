"""Optional LLM-steered parameter tuning for the auto-vectorizer.

A Claude vision model compares the source image to the current vector render
and proposes parameter changes (from a fixed allowed set) to improve the trace.
The model NEVER emits SVG — only a small JSON delta. Requires the optional
`[llm]` extra (anthropic) and an API key; the CLI falls back to the deterministic
loop when either is missing.
"""

import base64
import io
import json

from PIL import Image

from .autotune import render_svg, score
from .preprocess import quantize
from .vectorize import vectorize

# Parameters the LLM may tune, with their allowed values. Anything outside these
# sets (or any other key, including SVG content) is ignored — the LLM cannot
# steer the tracer outside this envelope.
ALLOWED = {
    "color_precision": [2, 3, 4, 5, 6, 7, 8],
    "filter_speckle": [0, 1, 2, 4, 6, 8, 10, 12],
    "corner_threshold": [30, 40, 50, 60, 70, 80],
    "mode": ["spline", "polygon"],
}


def apply_suggestion(current_params, suggestion):
    """Return a copy of current_params with only valid, allowed deltas applied."""
    out = dict(current_params)
    for key, allowed_values in ALLOWED.items():
        if key in suggestion and suggestion[key] in allowed_values:
            out[key] = suggestion[key]
    return out


def _flatten(img_rgba):
    bg = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img_rgba).convert("RGB")


def _trace(source_rgba, source_rgb, params, smooth):
    """Quantize + trace with params; return (svg, rendered_rgb, score)."""
    img_q = quantize(source_rgba, colors=params["colors"], smooth=smooth)
    svg = vectorize(img_q, params)
    rendered = render_svg(svg, source_rgba.size)
    return svg, rendered, score(rendered, source_rgb)


def llm_refine_vectorize(source_rgba, base_params, smooth=True, budget=6, suggest=None):
    """Tune tracing params using an LLM `suggest` callable, keeping the best result.

    `suggest(source_rgb, candidate_rgb, current_params) -> dict` returns a JSON
    delta (with an optional "done" flag). Each suggestion is validated by
    apply_suggestion, the candidate is traced/rendered/scored, and the best
    result is kept (never worse than the baseline). The loop stops on `done`,
    no change, or `budget` evaluations.

    If the VERY FIRST suggest() call raises (e.g. missing API key), the error
    propagates so the caller can fall back to the deterministic loop. Errors
    after at least one successful suggestion just end the loop with the best
    result so far. Returns (best_svg, best_params, best_score, evals).
    """
    source_rgb = _flatten(source_rgba)
    params = dict(base_params)

    best_svg, best_render, best_score = _trace(source_rgba, source_rgb, params, smooth)
    best_params = params
    evals = 1
    succeeded = False

    while evals < budget:
        try:
            suggestion = suggest(source_rgb, best_render, best_params)
        except Exception:
            if not succeeded:
                raise
            break
        succeeded = True

        if not suggestion or suggestion.get("done"):
            break
        candidate = apply_suggestion(best_params, suggestion)
        if candidate == best_params:
            break

        svg, rendered, candidate_score = _trace(source_rgba, source_rgb, candidate, smooth)
        evals += 1
        if candidate_score > best_score:
            best_svg, best_render, best_score, best_params = (
                svg, rendered, candidate_score, candidate,
            )

    return best_svg, best_params, best_score, evals
