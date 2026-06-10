"""Orchestrate generate -> render -> revise rounds into a final sprite."""

from .extract_svg import extract_svg
from .util import b64, media_type_for
from .validate import validate


def generate_engine(photo_path, generate, revise, render, exemplars,
                    conventions, rounds=3):
    """Author an engine sprite from a photo, refining it over `rounds`.

    Returns (svg, report). `generate`/`revise`/`render` are injected so this is
    testable without the network. The loop stops early when a revise returns an
    unchanged SVG or render fails. `report` is the validate() result.
    """
    with open(photo_path, "rb") as fh:
        photo_b64 = b64(fh.read())
    media = media_type_for(photo_path)

    svg = extract_svg(generate(photo_b64, media, exemplars, conventions))

    for _ in range(max(0, rounds - 1)):
        try:
            render_b64 = b64(render(svg))
        except Exception:
            break
        revised = extract_svg(revise(photo_b64, media, render_b64, svg, conventions))
        if revised.strip() == svg.strip():
            break
        svg = revised

    return svg, validate(svg)
