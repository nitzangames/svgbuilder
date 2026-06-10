"""Extract a single <svg>...</svg> element from an LLM reply."""

import re

_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)


def extract_svg(text):
    """Return the first <svg>...</svg> markup in `text` (ignoring fences/prose).

    Raises ValueError if no <svg> element is present.
    """
    match = _SVG_RE.search(text)
    if not match:
        raise ValueError("no <svg> element found in reply")
    return match.group(0).strip()
