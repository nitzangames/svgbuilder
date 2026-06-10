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

DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM = (
    "You tune a raster-to-SVG vectorizer (VTracer). You are shown a SOURCE "
    "image and the CURRENT vector render of it, plus the current parameters. "
    "Suggest parameter changes that make the render match the source more "
    "faithfully while staying clean and simple. You may ONLY change these "
    "parameters: color_precision (2-8; higher = more colors/detail), "
    "filter_speckle (0-12; higher = removes more small specks), "
    "corner_threshold (30-80 degrees; higher = smoother corners), and "
    "mode ('spline' for smooth curves or 'polygon' for crisp edges). "
    "Return ONLY the parameters you want to change. Set done=true when the "
    "render is already a good, clean match. Never output SVG."
)

# JSON schema for the constrained delta the model returns.
_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "color_precision": {"type": "integer", "enum": ALLOWED["color_precision"]},
        "filter_speckle": {"type": "integer", "enum": ALLOWED["filter_speckle"]},
        "corner_threshold": {"type": "integer", "enum": ALLOWED["corner_threshold"]},
        "mode": {"type": "string", "enum": ALLOWED["mode"]},
        "done": {"type": "boolean"},
    },
    "required": ["done"],
    "additionalProperties": False,
}


def _png_b64(img_rgb):
    buf = io.BytesIO()
    img_rgb.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


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


def make_suggester(model=DEFAULT_MODEL, client=None):
    """Build a suggest(source_rgb, candidate_rgb, current_params) -> dict callable
    backed by the Anthropic vision API. Lazily creates a default client if none
    is given. The returned dict is the validated-by-schema JSON delta."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    def suggest(source_rgb, candidate_rgb, current_params):
        shown = {k: current_params[k] for k in ALLOWED if k in current_params}
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "SOURCE image:"},
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png",
                        "data": _png_b64(source_rgb)}},
                    {"type": "text", "text": "CURRENT vector render:"},
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png",
                        "data": _png_b64(candidate_rgb)}},
                    {"type": "text", "text":
                        f"Current parameters: {json.dumps(shown)}. Suggest changes "
                        "to improve fidelity, or set done=true if it's already good."},
                ],
            }],
            output_config={"format": {"type": "json_schema", "schema": _DELTA_SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    return suggest
