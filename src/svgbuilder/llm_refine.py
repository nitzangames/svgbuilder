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
