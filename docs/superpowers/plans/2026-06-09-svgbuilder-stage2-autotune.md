# svgbuilder Stage 2 (`--auto` deterministic critic loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `--auto` mode that renders each candidate SVG, scores it against the source image with SSIM, searches the VTracer parameter space by coordinate descent, and keeps the best-scoring result — no LLM, fully deterministic.

**Architecture:** A new `autotune.py` module owns three concerns: render an SVG to raster (`resvg_py`, cairosvg fallback), score a render vs. the source (SSIM via scikit-image), and run the search loop (`auto_vectorize`). The CLI gains a `--auto` flag that, when set, routes through the loop instead of a single trace. The heavy deps (renderer + scikit-image) live behind a `[auto]` optional extra, lazily imported so the base tool stays light.

**Tech Stack:** Python 3.10–3.13 (project runs on the existing `.venv` = Python 3.12), resvg-py, scikit-image, numpy, plus the existing vtracer/pillow pipeline.

**Environment note:** Run everything with `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python` (Python 3.12). System `python3` is 3.14 and has a broken vtracer wheel — never use it.

---

## File Structure

- Modify: `pyproject.toml` — add `[auto]` optional-dependency group.
- Create: `tests/fixtures/sample.png` — a small committed multi-color test image (so tests run against a real raster file).
- Create: `tests/fixtures/__init__.py` — (none; fixtures dir holds data only — no init needed).
- Create: `src/svgbuilder/autotune.py` — `render_svg`, `score`, `auto_vectorize`.
- Modify: `src/svgbuilder/cli.py` — add `--auto` / `--auto-budget`, wire to `auto_vectorize` with a lazy import + friendly error if `[auto]` deps are missing.
- Create: `tests/test_autotune.py` — unit tests for render/score/loop.
- Modify: `tests/test_cli.py` — add an end-to-end `--auto` test.
- Modify: `README.md` — document `--auto` and the `[auto]` extra.

The auto-tune loop re-quantizes per candidate, so `auto_vectorize` takes the **loaded (downscaled) RGBA source** and calls the existing `preprocess.quantize` + `vectorize.vectorize` internally — no duplication of those steps.

---

### Task 1: Add the `[auto]` optional-dependency extra

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the `auto` extra**

In `pyproject.toml`, change the `[project.optional-dependencies]` table from:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
```
to:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
auto = [
    "resvg-py>=0.1.5",
    "scikit-image>=0.21",
    "numpy>=1.24",
]
```

- [ ] **Step 2: Install the project with auto + dev extras**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
.venv/bin/python -m pip install -e ".[auto,dev]"
```
Expected: installs `resvg-py`, `scikit-image`, `numpy` (and their deps) with no errors. Verify:
```bash
.venv/bin/python -c "import resvg_py, skimage, numpy; from skimage.metrics import structural_similarity; print('auto deps OK')"
```
Expected: prints `auto deps OK`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add [auto] optional-dependency extra for Stage 2

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add a committed test-fixture image

**Files:**
- Create: `tests/fixtures/sample.png`

- [ ] **Step 1: Generate the fixture deterministically**

Run this exact snippet (it draws a small flat-color "engine-ish" sprite — a handful of color regions so tracing produces several paths the loop can optimize):
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
mkdir -p tests/fixtures
.venv/bin/python - <<'EOF'
from PIL import Image, ImageDraw
img = Image.new("RGB", (96, 64), (245, 245, 245))   # off-white background
d = ImageDraw.Draw(img)
d.rectangle([8, 30, 70, 50], fill=(30, 110, 70))     # green body
d.rectangle([8, 26, 70, 30], fill=(200, 170, 60))    # gold trim stripe
d.rectangle([55, 16, 80, 50], fill=(20, 20, 20))     # black cab
d.ellipse([14, 44, 30, 60], fill=(15, 15, 15))       # front wheel
d.ellipse([40, 44, 56, 60], fill=(15, 15, 15))       # rear wheel
img.save("tests/fixtures/sample.png")
print("wrote tests/fixtures/sample.png", img.size, "colors:", len(img.getcolors(maxcolors=100)))
EOF
```
Expected: prints the size `(96, 64)` and a small color count (around 5–6).

- [ ] **Step 2: Verify it loads through the existing pipeline**

Run:
```bash
.venv/bin/python -c "
from svgbuilder.preprocess import load_image, quantize
from svgbuilder.presets import get_preset
from svgbuilder.vectorize import vectorize
img = load_image('tests/fixtures/sample.png', max_size=1000, bg='auto')
img = quantize(img, colors=8, smooth=False)
svg = vectorize(img, get_preset('clean'))
print('paths:', svg.count('<path'))
assert '<path' in svg
print('fixture OK')
"
```
Expected: prints a path count ≥ 1 and `fixture OK`.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/sample.png
git commit -m "test: add committed sample fixture image

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `render_svg` — rasterize an SVG string

**Files:**
- Create: `src/svgbuilder/autotune.py`
- Test: `tests/test_autotune.py`

- [ ] **Step 1: Write the failing test**

`tests/test_autotune.py`:
```python
from svgbuilder.autotune import render_svg

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
    '<rect width="20" height="10" fill="rgb(200,30,30)"/></svg>'
)


def test_render_svg_returns_rgb_image_of_requested_size():
    img = render_svg(_SVG, (20, 10))
    assert img.size == (20, 10)
    assert img.mode == "RGB"
    # the rect is solid red; center pixel should be reddish
    r, g, b = img.getpixel((10, 5))
    assert r > 150 and g < 100 and b < 100


def test_render_svg_resizes_to_requested_size():
    img = render_svg(_SVG, (40, 20))
    assert img.size == (40, 20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.autotune'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/autotune.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/autotune.py tests/test_autotune.py
git commit -m "feat: add SVG rasterization (render_svg) for auto-tuning

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `score` — SSIM between a render and the source

**Files:**
- Modify: `src/svgbuilder/autotune.py`
- Test: `tests/test_autotune.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_autotune.py`)**

Add these imports/tests to the existing `tests/test_autotune.py`:
```python
from PIL import Image as _Image
from svgbuilder.autotune import score


def test_score_identical_images_is_near_one():
    img = _Image.new("RGB", (32, 32), (30, 110, 70))
    assert score(img, img) > 0.99


def test_score_different_images_is_lower_than_identical():
    a = _Image.new("RGB", (32, 32), (30, 110, 70))
    b = _Image.new("RGB", (32, 32), (200, 30, 30))
    assert score(a, b) < score(a, a)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -k score -v`
Expected: FAIL with `ImportError: cannot import name 'score'`.

- [ ] **Step 3: Add the implementation to `src/svgbuilder/autotune.py`**

Append after `render_svg`:
```python
def score(candidate_rgb, source_rgb):
    """Color-aware SSIM between two equal-size RGB images. Higher is closer.

    Returns a float in roughly [-1, 1]; 1.0 means identical.
    """
    a = np.asarray(candidate_rgb, dtype=np.float64)
    b = np.asarray(source_rgb, dtype=np.float64)
    return float(structural_similarity(a, b, channel_axis=2, data_range=255.0))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -v`
Expected: PASS (4 passed total in this file).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/autotune.py tests/test_autotune.py
git commit -m "feat: add SSIM scoring for auto-tuning

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `auto_vectorize` — the coordinate-descent loop

**Files:**
- Modify: `src/svgbuilder/autotune.py`
- Test: `tests/test_autotune.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_autotune.py`)**

```python
from svgbuilder.autotune import auto_vectorize
from svgbuilder.preprocess import load_image
from svgbuilder.presets import get_preset

_FIXTURE = "tests/fixtures/sample.png"


def test_auto_vectorize_returns_svg_and_respects_budget():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")
    svg, params, best, evals = auto_vectorize(src, get_preset("clean"), smooth=False, budget=5)
    assert "<path" in svg
    assert 1 <= evals <= 5
    assert -1.0 <= best <= 1.0
    assert isinstance(params, dict) and "color_precision" in params


def test_auto_vectorize_never_worse_than_baseline():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")
    base = get_preset("clean")
    # baseline single-trace score
    from svgbuilder.autotune import render_svg, score
    from svgbuilder.preprocess import quantize
    from svgbuilder.vectorize import vectorize
    src_rgb = src.convert("RGB")
    base_svg = vectorize(quantize(src, colors=base["colors"], smooth=False), base)
    base_score = score(render_svg(base_svg, src.size), src_rgb)
    # auto result
    _svg, _params, best, _evals = auto_vectorize(src, base, smooth=False, budget=6)
    assert best >= base_score - 1e-9   # best kept is never worse than the baseline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -k auto_vectorize -v`
Expected: FAIL with `ImportError: cannot import name 'auto_vectorize'`.

- [ ] **Step 3: Add the implementation to `src/svgbuilder/autotune.py`**

Append after `score`:
```python
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
    seen (never worse than the baseline). Stops at `budget` evaluations or when
    a full pass yields no improvement.

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_autotune.py -v`
Expected: PASS (all autotune tests green). This runs real tracing+rendering several times, so it may take a few seconds.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/autotune.py tests/test_autotune.py
git commit -m "feat: add coordinate-descent auto_vectorize loop

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire `--auto` into the CLI

**Files:**
- Modify: `src/svgbuilder/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_main_auto_flag_writes_svg(tmp_path):
    out = tmp_path / "auto.svg"
    exit_code = main([
        "tests/fixtures/sample.png", "-o", str(out),
        "--auto", "--auto-budget", "3", "--no-smooth", "--quiet",
    ])
    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_cli.py::test_main_auto_flag_writes_svg -v`
Expected: FAIL — `main` does not yet accept `--auto` (argparse error / SystemExit).

- [ ] **Step 3: Add the flags to the parser**

In `src/svgbuilder/cli.py`, inside `_build_parser()`, add these two arguments immediately before the `--quiet` argument:
```python
    p.add_argument("--auto", action="store_true",
                   help="Auto-tune tracing parameters by rendering and scoring "
                        "candidates (needs the [auto] extra).")
    p.add_argument("--auto-budget", type=int, default=6, dest="auto_budget",
                   help="Max candidate evaluations for --auto (default 6).")
```

- [ ] **Step 4: Route through the loop in `main`**

In `src/svgbuilder/cli.py`, replace this block inside `main`:
```python
    try:
        params = build_params(args.preset, args.colors, args.filter_speckle, args.mode)
        img = load_image(args.input, max_size=args.max_size, bg=args.bg)
        img = quantize(img, colors=params["colors"], smooth=not args.no_smooth)
        svg = vectorize(img, params)
    except Exception as exc:  # surface a clean message, not a traceback
        print(f"error: failed to vectorize {args.input}: {exc}", file=sys.stderr)
        return 1
```
with:
```python
    auto_info = None
    try:
        params = build_params(args.preset, args.colors, args.filter_speckle, args.mode)
        img = load_image(args.input, max_size=args.max_size, bg=args.bg)
        if args.auto:
            try:
                from .autotune import auto_vectorize
            except ImportError:
                print("error: --auto needs the [auto] extra. Install it with: "
                      "pip install 'svgbuilder[auto]'", file=sys.stderr)
                return 1
            svg, params, best_score, evals = auto_vectorize(
                img, params, smooth=not args.no_smooth, budget=args.auto_budget
            )
            auto_info = f"auto: score={best_score:.3f} in {evals} evals"
        else:
            img = quantize(img, colors=params["colors"], smooth=not args.no_smooth)
            svg = vectorize(img, params)
    except Exception as exc:  # surface a clean message, not a traceback
        print(f"error: failed to vectorize {args.input}: {exc}", file=sys.stderr)
        return 1
```

- [ ] **Step 5: Include auto stats in the success line**

In `src/svgbuilder/cli.py`, replace the success-print block:
```python
    if not args.quiet:
        print(f"wrote {out_path}  "
              f"(colors={params['colors']}, paths={svg.count('<path')}, "
              f"bytes={len(svg)})")
    return 0
```
with:
```python
    if not args.quiet:
        line = (f"wrote {out_path}  "
                f"(colors={params['colors']}, paths={svg.count('<path')}, "
                f"bytes={len(svg)})")
        if auto_info:
            line += f"  [{auto_info}]"
        print(line)
    return 0
```

- [ ] **Step 6: Run the CLI test, then the full suite**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS (6 prior + 1 new = 7 passed).

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q`
Expected: all tests pass (presets, preprocess, vectorize, cli, autotune).

- [ ] **Step 7: Commit**

```bash
git add src/svgbuilder/cli.py tests/test_cli.py
git commit -m "feat: add --auto deterministic auto-tuning to the CLI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: README, real-image smoke test, final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `--auto` in the README**

In `README.md`, add `--auto` to the Options list (after the `--bg` line) and a short section. Insert after the existing Options list:
```markdown
### Auto-tuning (`--auto`)

With the `[auto]` extra installed (`pip install 'svgbuilder[auto]'`), `--auto`
renders each candidate SVG, scores it against the source with SSIM, and searches
the tracing parameters to keep the best-looking result:

    svgbuilder train.jpg --auto                 # default budget of 6 evaluations
    svgbuilder train.jpg --auto --auto-budget 10

It is fully deterministic and offline (no LLM). The success line then also
reports the best score and how many candidates were evaluated.
```
Also add this bullet to the Options list, right after the `--bg` bullet:
```markdown
- `--auto`                tune params by render+score (needs the `[auto]` extra)
- `--auto-budget N`       max candidate evaluations for `--auto` (default 6)
```

- [ ] **Step 2: Real-image smoke test (baseline vs auto)**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
IMG="/Users/nitzanwilnai/Downloads/TrainGame/Engines/4-4-0 American 4.jpg"
.venv/bin/svgbuilder "$IMG" -o /tmp/eng_base.svg --preset clean
.venv/bin/svgbuilder "$IMG" -o /tmp/eng_auto.svg --preset clean --auto --auto-budget 8
ls -l /tmp/eng_base.svg /tmp/eng_auto.svg
```
Expected: both succeed (exit 0); the `--auto` run prints a `[auto: score=… in N evals]` suffix. Confirm the auto SVG is valid (`head -c 80 /tmp/eng_auto.svg` shows `<?xml`/`<svg`).

- [ ] **Step 3: Final full-suite run**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q && .venv/bin/svgbuilder --help`
Expected: all tests pass and `--help` lists `--auto` and `--auto-budget`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document --auto auto-tuning mode

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes / deferred
- **DreamSim perceptual scoring** (the design's optional `[perceptual]` extra, pulls torch) is intentionally NOT built here — SSIM is the Stage 2 default and is enough to demonstrate and ship the loop. DreamSim can be added later as an alternate scorer behind a `--metric` flag.
- **`mode` (spline/polygon) is not in the search space** — Stage 2 searches `color_precision`, `filter_speckle`, and `corner_threshold` to bound cost. Adding `mode` later is a one-line `_SEARCH` change.
- **Stage 3 (`--llm-refine`)** remains future work with its own plan.
