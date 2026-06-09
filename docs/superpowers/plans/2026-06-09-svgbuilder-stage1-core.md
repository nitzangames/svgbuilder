# svgbuilder Stage 1 (Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, installable Python CLI (`svgbuilder`) that converts one raster image into a clean, simplified colored SVG using a deterministic Pillow-quantize → VTracer pipeline.

**Architecture:** A small `src/`-layout package. `cli.py` orchestrates: `preprocess.py` loads + downscales + palette-quantizes the image, `vectorize.py` traces it with VTracer using parameters from `presets.py`. Pure, deterministic, offline. Stages 2 (`--auto`) and 3 (`--llm-refine`) are separate later plans.

**Tech Stack:** Python 3.10+, Pillow, vtracer (Rust-backed, cp314 wheels confirmed), pytest, hatchling.

---

## File Structure

- `pyproject.toml` — package metadata, deps, console entry point.
- `README.md` — install + usage + worked example.
- `LICENSE` — MIT.
- `src/svgbuilder/__init__.py` — version.
- `src/svgbuilder/presets.py` — named presets → parameter dicts.
- `src/svgbuilder/preprocess.py` — load, downscale, denoise, quantize.
- `src/svgbuilder/vectorize.py` — VTracer invocation + parameter mapping.
- `src/svgbuilder/cli.py` — argparse, orchestration, output-path derivation, stats, exit codes.
- `tests/test_presets.py`, `tests/test_preprocess.py`, `tests/test_vectorize.py`, `tests/test_cli.py`.

---

### Task 1: Project scaffold, packaging, and dependency verification

**Files:**
- Create: `pyproject.toml`
- Create: `src/svgbuilder/__init__.py`
- Create: `tests/__init__.py`
- Create: `LICENSE`

- [ ] **Step 1: Initialize git (repo does not yet exist)**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
git init
printf '__pycache__/\n*.pyc\n.venv/\nbuild/\ndist/\n*.egg-info/\n.pytest_cache/\n' > .gitignore
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "svgbuilder"
version = "0.1.0"
description = "Convert a raster image into a clean, simplified colored SVG."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
authors = [{ name = "nitzanwilnai" }]
dependencies = [
    "vtracer>=0.6.15",
    "pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
svgbuilder = "svgbuilder.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/svgbuilder"]
```

- [ ] **Step 3: Create package + test init files**

`src/svgbuilder/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
```

`LICENSE`: standard MIT license text (year 2026, author nitzanwilnai).

- [ ] **Step 4: Install in editable mode with dev extras**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
python3 -m pip install -e ".[dev]"
```
Expected: installs `vtracer`, `pillow`, `pytest`, and `svgbuilder` itself, with no source-build of vtracer (prebuilt cp314 wheel). If vtracer fails to install, STOP and report — do not proceed.

- [ ] **Step 5: Verify the real vtracer API signature before writing code against it**

Run:
```bash
python3 -c "import vtracer, inspect; print([n for n in dir(vtracer) if 'svg' in n]); print(inspect.signature(vtracer.convert_pixels_to_svg))"
```
Expected: lists `convert_pixels_to_svg` (and `convert_image_to_svg_py`) and prints its parameter names. **Record the exact parameter names** — Task 4 maps to them. If a kwarg name differs from this plan (e.g. `colormode` vs `color_mode`), use the name reported here.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold svgbuilder package and packaging"
```

---

### Task 2: Presets

**Files:**
- Create: `src/svgbuilder/presets.py`
- Test: `tests/test_presets.py`

- [ ] **Step 1: Write the failing test**

`tests/test_presets.py`:
```python
import pytest
from svgbuilder.presets import get_preset, PRESET_NAMES


def test_clean_is_default_with_16_colors():
    p = get_preset("clean")
    assert p["colors"] == 16
    assert p["mode"] == "spline"
    assert p["color_precision"] == 4


def test_flat_is_8_colors():
    assert get_preset("flat")["colors"] == 8


def test_detailed_is_24_colors():
    assert get_preset("detailed")["colors"] == 24


def test_returns_a_copy_not_shared_state():
    a = get_preset("clean")
    a["colors"] = 999
    assert get_preset("clean")["colors"] == 16


def test_unknown_preset_raises_valueerror():
    with pytest.raises(ValueError):
        get_preset("nope")


def test_preset_names_listed():
    assert set(PRESET_NAMES) == {"flat", "clean", "detailed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_presets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.presets'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/presets.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_presets.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/presets.py tests/test_presets.py
git commit -m "feat: add tracing presets (flat/clean/detailed)"
```

---

### Task 3: Preprocessing (load, downscale, quantize)

**Files:**
- Create: `src/svgbuilder/preprocess.py`
- Test: `tests/test_preprocess.py`

- [ ] **Step 1: Write the failing test**

`tests/test_preprocess.py`:
```python
from PIL import Image
from svgbuilder.preprocess import load_image, quantize


def _gradient(w, h):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    return img.convert("RGBA")


def test_load_downscales_to_max_size(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (2000, 1000)).save(src)
    img = load_image(str(src), max_size=500, bg="auto")
    assert max(img.size) == 500
    assert img.mode == "RGBA"


def test_load_keeps_small_image_unchanged(tmp_path):
    src = tmp_path / "small.png"
    Image.new("RGB", (100, 80)).save(src)
    img = load_image(str(src), max_size=500, bg="auto")
    assert img.size == (100, 80)


def test_load_white_bg_flattens_alpha(tmp_path):
    src = tmp_path / "alpha.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(src)
    img = load_image(str(src), max_size=500, bg="white")
    assert img.getpixel((0, 0)) == (255, 255, 255, 255)


def test_quantize_reduces_distinct_colors():
    img = _gradient(64, 64)
    q = quantize(img, colors=8, smooth=False)
    distinct = {p for p in q.getdata()}
    assert len(distinct) <= 8
    assert q.mode == "RGBA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_preprocess.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.preprocess'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/preprocess.py`:
```python
"""Load and prepare a raster image for tracing."""

from PIL import Image, ImageFilter


def load_image(path, max_size=1000, bg="auto"):
    """Open an image as RGBA, optionally flatten background, and downscale.

    bg: "white" flattens transparency onto white; "none"/"auto" preserve alpha.
    max_size: longest-edge cap in pixels; larger images are downscaled.
    """
    img = Image.open(path).convert("RGBA")

    if bg == "white":
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)

    longest = max(img.size)
    if longest > max_size:
        scale = max_size / longest
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    return img


def quantize(img, colors=16, smooth=True):
    """Reduce the image to a fixed palette (deterministic, no dithering)."""
    if smooth:
        img = img.filter(ImageFilter.MedianFilter(size=3))
    q = img.quantize(
        colors=colors,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    )
    return q.convert("RGBA")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_preprocess.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/preprocess.py tests/test_preprocess.py
git commit -m "feat: add image loading, downscaling, and quantization"
```

---

### Task 4: Vectorization (VTracer)

**Files:**
- Create: `src/svgbuilder/vectorize.py`
- Test: `tests/test_vectorize.py`

> NOTE: Use the exact kwarg names recorded in Task 1, Step 5. The names below match vtracer 0.6.15's documented Python API; adjust if Step 5 reported otherwise.

- [ ] **Step 1: Write the failing test**

`tests/test_vectorize.py`:
```python
from PIL import Image
from svgbuilder.presets import get_preset
from svgbuilder.vectorize import vectorize


def _two_color_image():
    img = Image.new("RGBA", (32, 32), (0, 128, 0, 255))
    for y in range(32):
        for x in range(16):
            img.putpixel((x, y), (200, 30, 30, 255))
    return img


def test_vectorize_returns_svg_with_paths():
    svg = vectorize(_two_color_image(), get_preset("clean"))
    assert isinstance(svg, str)
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    assert "<path" in svg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_vectorize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.vectorize'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/vectorize.py`:
```python
"""Trace a prepared RGBA image into an SVG string using VTracer."""

import vtracer


def vectorize(img_rgba, params):
    """Convert an RGBA PIL image to an SVG string using preset parameters."""
    pixels = list(img_rgba.getdata())
    return vtracer.convert_pixels_to_svg(
        pixels,
        size=img_rgba.size,
        colormode="color",
        hierarchical="stacked",
        mode=params["mode"],
        filter_speckle=params["filter_speckle"],
        color_precision=params["color_precision"],
        layer_difference=params["layer_difference"],
        corner_threshold=params["corner_threshold"],
        length_threshold=params["length_threshold"],
        max_iterations=10,
        splice_threshold=params["splice_threshold"],
        path_precision=8,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_vectorize.py -v`
Expected: PASS (1 passed). If it fails on a `TypeError` about an argument name or positional `size`, fix the call to match the signature recorded in Task 1 Step 5, then re-run.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/vectorize.py tests/test_vectorize.py
git commit -m "feat: add VTracer vectorization step"
```

---

### Task 5: CLI orchestration

**Files:**
- Create: `src/svgbuilder/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from PIL import Image
from svgbuilder.cli import derive_output_path, build_params, main


def test_derive_output_path_defaults_next_to_input():
    assert derive_output_path("/a/b/train.jpg", None) == "/a/b/train.svg"


def test_derive_output_path_respects_explicit():
    assert derive_output_path("/a/b/train.jpg", "/out/x.svg") == "/out/x.svg"


def test_build_params_applies_preset_then_overrides():
    p = build_params(preset="clean", colors=None)
    assert p["colors"] == 16
    p2 = build_params(preset="clean", colors=5)
    assert p2["colors"] == 5  # explicit flag overrides preset


def test_main_end_to_end_writes_valid_svg(tmp_path):
    src = tmp_path / "in.png"
    img = Image.new("RGBA", (24, 24), (0, 128, 0, 255))
    for x in range(12):
        for y in range(24):
            img.putpixel((x, y), (200, 30, 30, 255))
    img.save(src)
    out = tmp_path / "out.svg"

    exit_code = main([str(src), "-o", str(out), "--quiet"])

    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text


def test_main_missing_file_returns_nonzero(tmp_path):
    exit_code = main([str(tmp_path / "nope.png"), "--quiet"])
    assert exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.cli'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/cli.py`:
```python
"""Command-line interface for svgbuilder."""

import argparse
import os
import sys

from . import __version__
from .presets import DEFAULT_PRESET, PRESET_NAMES, get_preset
from .preprocess import load_image, quantize
from .vectorize import vectorize


def derive_output_path(input_path, output):
    if output:
        return output
    base, _ = os.path.splitext(input_path)
    return base + ".svg"


def build_params(preset, colors=None, filter_speckle=None, mode=None):
    params = get_preset(preset)
    if colors is not None:
        params["colors"] = colors
    if filter_speckle is not None:
        params["filter_speckle"] = filter_speckle
    if mode is not None:
        params["mode"] = mode
    return params


def _build_parser():
    p = argparse.ArgumentParser(
        prog="svgbuilder",
        description="Convert a raster image into a clean, simplified colored SVG.",
        epilog="Example: svgbuilder train.jpg --preset clean -o train.svg",
    )
    p.add_argument("input", help="Path to the input image (jpg/webp/png).")
    p.add_argument("-o", "--output", help="Output .svg path (default: alongside input).")
    p.add_argument("--preset", choices=PRESET_NAMES, default=DEFAULT_PRESET,
                   help=f"Tracing preset (default: {DEFAULT_PRESET}).")
    p.add_argument("--colors", type=int, help="Override palette size (e.g. 8, 16, 24).")
    p.add_argument("--filter-speckle", type=int, dest="filter_speckle",
                   help="Override speckle filter size (higher = cleaner).")
    p.add_argument("--mode", choices=["spline", "polygon"],
                   help="Override curve mode (spline=smooth, polygon=crisp).")
    p.add_argument("--max-size", type=int, default=1000, dest="max_size",
                   help="Downscale so the longest edge is at most this (default 1000).")
    p.add_argument("--no-smooth", action="store_true",
                   help="Disable median-filter denoising before quantization.")
    p.add_argument("--bg", choices=["auto", "white", "none"], default="auto",
                   help="Background handling for transparent images.")
    p.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    p.add_argument("--version", action="version", version=f"svgbuilder {__version__}")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    try:
        params = build_params(args.preset, args.colors, args.filter_speckle, args.mode)
        img = load_image(args.input, max_size=args.max_size, bg=args.bg)
        img = quantize(img, colors=params["colors"], smooth=not args.no_smooth)
        svg = vectorize(img, params)
    except Exception as exc:  # surface a clean message, not a traceback
        print(f"error: failed to vectorize {args.input}: {exc}", file=sys.stderr)
        return 1

    out_path = derive_output_path(args.input, args.output)
    try:
        with open(out_path, "w") as fh:
            fh.write(svg)
    except OSError as exc:
        print(f"error: could not write {out_path}: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"wrote {out_path}  "
              f"(colors={params['colors']}, paths={svg.count('<path')}, "
              f"bytes={len(svg)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 6: Commit**

```bash
git add src/svgbuilder/cli.py tests/test_cli.py
git commit -m "feat: add CLI orchestration and end-to-end pipeline"
```

---

### Task 6: Real-image smoke test, README, and final verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the tool on a real locomotive image**

Run:
```bash
svgbuilder "/Users/nitzanwilnai/Downloads/TrainGame/Engines/4-4-0 American 4.jpg" \
  -o /tmp/train_clean.svg --preset clean
svgbuilder "/Users/nitzanwilnai/Downloads/TrainGame/Engines/4-4-0 American 4.jpg" \
  -o /tmp/train_flat.svg --preset flat
```
Expected: both commands exit 0 and print stats. Confirm the files exist and are non-trivial:
```bash
ls -l /tmp/train_clean.svg /tmp/train_flat.svg
head -c 200 /tmp/train_clean.svg
```
Expected: each file is several KB+, starts with `<?xml`/`<svg`, and `flat` is smaller (fewer paths) than `clean`. Open them in a browser to eyeball quality.

- [ ] **Step 2: Write `README.md`**

```markdown
# svgbuilder

Convert a raster image (jpg/webp/png) into a clean, simplified colored SVG.
One image per run. Deterministic, offline, scriptable.

## Install

    pipx install svgbuilder        # or: pip install .

Requires Python 3.10+. Pulls in `vtracer` and `pillow`.

## Usage

    svgbuilder INPUT [-o OUT] [--preset clean|flat|detailed] [options]

Examples:

    svgbuilder train.jpg                      # -> train.svg (clean preset)
    svgbuilder train.jpg --preset flat        # poster-like, ~8 colors
    svgbuilder train.jpg --colors 12 -o out.svg
    svgbuilder sprite.png --bg none           # preserve transparency

### Presets

| Preset     | Colors | Look                              |
|------------|--------|-----------------------------------|
| `flat`     | 8      | Flat, poster-like, fewest paths   |
| `clean`    | 16     | Clean simplified (default)        |
| `detailed` | 24     | More faithful, larger file        |

### Options

- `--colors N`        override palette size
- `--filter-speckle N` higher = removes more small specks
- `--mode spline|polygon` smooth curves vs crisp edges
- `--max-size PX`      downscale longest edge (default 1000)
- `--no-smooth`       disable denoising before quantization
- `--bg auto|white|none` background handling for transparent images
- `--quiet`           suppress non-error output

Exit code 0 on success; non-zero with a message on failure.

## How it works

`load → downscale → denoise → palette-quantize (Pillow FASTOCTREE) →
trace (VTracer spline) → write .svg`

## License

MIT
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with usage and presets"
```

- [ ] **Step 4: Final verification**

Run: `python3 -m pytest -v && svgbuilder --help`
Expected: all tests pass and `--help` prints full usage. Stage 1 is complete and shippable.

---

## Deferred to later plans
- **Stage 2 (`--auto`):** deterministic critic loop — render (resvg/cairosvg) → SSIM/DreamSim score → coordinate-descent over knobs → keep best. Adds `[auto]`/`[perceptual]` extras.
- **Stage 3 (`--llm-refine`):** optional LLM parameter-suggester returning constrained JSON deltas, with hard fallback to Stage 2. Adds `[llm]` extra.

Each will get its own `docs/superpowers/plans/` file after Stage 1 is verified.
