"""Advisory convention checks for a generated engine sprite."""

import re

WHEEL_FILL = "#2c2c2a"
WHEEL_MIN_RADIUS = 6.0

_CIRCLE_RE = re.compile(r"<circle\b[^>]*>", re.IGNORECASE)
# Match attributes in either single or double quotes.
_ATTR_RE = re.compile(r"""([\w-]+)\s*=\s*["']([^"']*)["']""")
_VIEWBOX_RE = re.compile(r"""viewbox\s*=\s*["']""", re.IGNORECASE)


def _circles(svg):
    out = []
    for tag in _CIRCLE_RE.findall(svg):
        attrs = dict(_ATTR_RE.findall(tag))
        try:
            out.append({
                "r": float(attrs.get("r", "0")),
                "fill": attrs.get("fill", "").strip().lower(),
            })
        except ValueError:
            continue
    return out


def validate(svg):
    """Return {has_viewbox, wheel_count, ok}.

    A wheel is a circle filled WHEEL_FILL with radius >= WHEEL_MIN_RADIUS — the
    same shape TrainGame's extract_assets.js detects. `ok` means the sprite has a
    viewBox and at least two such wheels.
    """
    has_viewbox = bool(_VIEWBOX_RE.search(svg))
    wheels = [c for c in _circles(svg)
              if c["fill"] == WHEEL_FILL and c["r"] >= WHEEL_MIN_RADIUS]
    return {
        "has_viewbox": has_viewbox,
        "wheel_count": len(wheels),
        "ok": has_viewbox and len(wheels) >= 2,
    }
