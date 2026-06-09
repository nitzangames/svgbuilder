"""Named tracing presets mapping to VTracer + quantization parameters."""

_PRESETS = {
    "flat": {
        "colors": 8,
        "color_precision": 3,
        "filter_speckle": 8,
        "layer_difference": 32,
        "corner_threshold": 70,
        "length_threshold": 6.0,
        "splice_threshold": 60,
        "mode": "spline",
    },
    "clean": {
        "colors": 16,
        "color_precision": 4,
        "filter_speckle": 6,
        "layer_difference": 24,
        "corner_threshold": 60,
        "length_threshold": 4.0,
        "splice_threshold": 45,
        "mode": "spline",
    },
    "detailed": {
        "colors": 24,
        "color_precision": 5,
        "filter_speckle": 4,
        "layer_difference": 16,
        "corner_threshold": 50,
        "length_threshold": 4.0,
        "splice_threshold": 45,
        "mode": "spline",
    },
}

PRESET_NAMES = tuple(_PRESETS.keys())
DEFAULT_PRESET = "clean"


def get_preset(name):
    """Return a fresh copy of the named preset's parameter dict."""
    if name not in _PRESETS:
        raise ValueError(
            f"Unknown preset {name!r}. Choose from: {', '.join(PRESET_NAMES)}"
        )
    return dict(_PRESETS[name])
