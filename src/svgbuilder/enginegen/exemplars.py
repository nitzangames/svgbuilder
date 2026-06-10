"""Load the bundled house-style exemplar sprites and the conventions prompt."""

import os
from importlib import resources

_STYLE_PKG = "svgbuilder.enginegen.style"
_DEFAULT = (
    "classic-american-4-4-0.svg",
    "cn-gp9-chopnose.svg",
    "saddle-tank-blue.svg",
)


def load_exemplars(extra_paths=None):
    """Return [(name, svg_text), ...] for the bundled exemplars plus any extras."""
    base = resources.files(_STYLE_PKG)
    out = [(name, base.joinpath(name).read_text()) for name in _DEFAULT]
    for path in extra_paths or []:
        with open(path) as fh:
            out.append((os.path.basename(path), fh.read()))
    return out


def load_conventions():
    """Return the conventions system-prompt text."""
    return resources.files(_STYLE_PKG).joinpath("conventions.md").read_text()
