# enginegen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `enginegen` command that turns a locomotive photo into a clean, house-style engine SVG sprite (resembling that engine) via a Claude vision generate→render→revise loop.

**Architecture:** A self-contained `svgbuilder.enginegen` subpackage. Pure helpers (`util`, `extract_svg`, `validate`, `render`, `exemplars`) are dependency-light and unit-tested; the Claude calls (`generate`/`revise`) and the orchestration `loop` take injected callables so they're testable without the network. The CLI wires it together. Output is one `.svg` (+ preview `.png`); the TrainGame pipeline owns extraction.

**Tech Stack:** Python 3.10–3.13 (project `.venv` = Python 3.12), `anthropic` (model `claude-opus-4-8`, vision + adaptive thinking), `resvg-py` (render), stdlib `re`/`base64`/`importlib.resources`.

**Environment note:** Run everything with `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python` (Python 3.12). Never use bare `python3`. Tests run from the project root. No `ANTHROPIC_API_KEY` is needed — every test injects fakes; the real call is exercised manually.

---

## File Structure

- Modify: `pyproject.toml` — `[engine]` extra + `enginegen` console script + bundle style data.
- Create: `src/svgbuilder/enginegen/__init__.py`
- Create: `src/svgbuilder/enginegen/style/classic-american-4-4-0.svg`, `cn-gp9-chopnose.svg`, `saddle-tank-blue.svg` (copied from TrainGame), `conventions.md` (the system prompt).
- Create: `src/svgbuilder/enginegen/util.py` — `b64`, `media_type_for`.
- Create: `src/svgbuilder/enginegen/extract_svg.py` — pull `<svg>…</svg>` from a reply.
- Create: `src/svgbuilder/enginegen/validate.py` — convention checks (wheels, viewBox).
- Create: `src/svgbuilder/enginegen/render.py` — SVG→PNG bytes via resvg.
- Create: `src/svgbuilder/enginegen/exemplars.py` — load bundled exemplars + conventions.
- Create: `src/svgbuilder/enginegen/generate.py` — `make_generator()` → `(generate, revise)`.
- Create: `src/svgbuilder/enginegen/loop.py` — `generate_engine(...)`.
- Create: `src/svgbuilder/enginegen/cli.py` — argparse + orchestration.
- Create: `tests/test_enginegen.py` — all unit/integration tests for the subpackage.

---

### Task 1: Scaffold the subpackage, bundle style data, add the `[engine]` extra

**Files:**
- Create: `src/svgbuilder/enginegen/__init__.py`, `src/svgbuilder/enginegen/style/*` (+ `conventions.md`)
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the package and copy the exemplar SVGs**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
mkdir -p src/svgbuilder/enginegen/style
printf '"""Photo -> house-style engine sprite generator."""\n' > src/svgbuilder/enginegen/__init__.py
SRC=/Users/nitzanwilnai/Programming/Claude/TrainGame/src/assets/engines
cp "$SRC/classic-american-4-4-0.svg" "$SRC/cn-gp9-chopnose.svg" "$SRC/saddle-tank-blue.svg" \
   src/svgbuilder/enginegen/style/
ls src/svgbuilder/enginegen/style/
```
Expected: the three `.svg` files are listed.

- [ ] **Step 2: Write the conventions system prompt**

Create `src/svgbuilder/enginegen/style/conventions.md`:
```markdown
You are an expert SVG illustrator creating side-profile locomotive sprites for a
2D train game, in a specific flat, hand-drawn house style.

OUTPUT RULES (critical):
- Output ONLY one self-contained <svg> element with a viewBox. No prose, no code
  fences, no <html>. It must be valid and render on its own.

STYLE:
- Flat color fills with slightly darker stroke outlines. No gradients or filters.
- Build the engine from simple primitives: <rect> (rx for rounded), <circle>,
  <line>, and <path> with Q/C curves. Add a short XML comment before each part.
- Side profile, facing RIGHT (front/smokebox to the right, cab/rear to the left).
- viewBox roughly 150-215 units wide, similar scale to the examples.

WHEELS (critical for the game engine that consumes this sprite):
- Draw the wheels FIRST so the body overlaps their tops.
- Each wheel is a <circle> filled "#2c2c2a" (optionally a "#cfcdc3" steel-tire
  ring circle behind it and a small dark hub on top; drivers get spoke <line>s).
- Use the correct number/arrangement for the prototype (a 4-4-0 = a 2-wheel
  leading bogie + 2 large drivers in profile; a 2-8-0 = 4 drivers; a B-B diesel =
  two bogies of 2). Drivers are large; pilot/bogie wheels are smaller.
- Position all wheels along the lower frame so their bottoms rest near the
  baseline. Each wheel circle must have radius >= 6 so the game detects it.

PALETTE:
- Match the SUBJECT's livery colors for the body/tank/tender (use what you see in
  the photo). For steam-era trim use gold "#d9a834"/"#f4c775"; steel "#cfcdc3";
  charcoals "#191919","#2c2c2a","#0e0e0e".

RESEMBLANCE:
- Capture the specific engine's identity: body color, wheel arrangement, and
  standout features (balloon vs straight stack, saddle tank, streamlining,
  cowcatcher, domes, headlamp, tender). It must read as THIS engine in the house
  style — not a generic engine, not a photo trace.
```

- [ ] **Step 3: Add the `[engine]` extra, console script, and bundle the style data**

In `pyproject.toml`, add to `[project.optional-dependencies]` (after `llm`):
```toml
engine = [
    "anthropic>=0.40",
    "resvg-py>=0.1.5",
]
```
In `[project.scripts]`, add a second entry so the table reads:
```toml
[project.scripts]
svgbuilder = "svgbuilder.cli:main"
enginegen = "svgbuilder.enginegen.cli:main"
```
Add this block so the non-`.py` style files are packaged into the wheel:
```toml
[tool.hatch.build.targets.wheel.force-include]
"src/svgbuilder/enginegen/style" = "svgbuilder/enginegen/style"
```

- [ ] **Step 4: Reinstall and verify the package + data import**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
.venv/bin/python -m pip install -e ".[auto,llm,engine,dev]"
.venv/bin/python -c "
from importlib import resources
p = resources.files('svgbuilder.enginegen.style')
print('conventions chars:', len(p.joinpath('conventions.md').read_text()))
print('exemplar chars:', len(p.joinpath('classic-american-4-4-0.svg').read_text()))
"
```
Expected: prints non-zero character counts for both. If install fails, STOP and report BLOCKED.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/svgbuilder/enginegen
git commit -m "feat(enginegen): scaffold subpackage, bundle style exemplars, add [engine] extra

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `util` — base64 + media type

**Files:**
- Create: `src/svgbuilder/enginegen/util.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Write the failing test** — `tests/test_enginegen.py`:
```python
import pytest
from svgbuilder.enginegen.util import b64, media_type_for


def test_b64_roundtrips_ascii():
    assert b64(b"PNG") == "UE5H"


def test_media_type_for_known_extensions():
    assert media_type_for("/a/x.jpg") == "image/jpeg"
    assert media_type_for("/a/x.jpeg") == "image/jpeg"
    assert media_type_for("/a/x.PNG") == "image/png"
    assert media_type_for("/a/x.webp") == "image/webp"


def test_media_type_for_unsupported_raises():
    with pytest.raises(ValueError):
        media_type_for("/a/x.gif")
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.enginegen.util'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/util.py`:
```python
"""Small helpers for the engine generator."""

import base64
import os

_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def b64(data):
    """Base64-encode bytes to an ASCII string."""
    return base64.standard_b64encode(data).decode("ascii")


def media_type_for(path):
    """Map an image path's extension to its image/* media type."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _MEDIA:
        raise ValueError(f"unsupported image type: {ext or '(none)'}")
    return _MEDIA[ext]
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/util.py tests/test_enginegen.py
git commit -m "feat(enginegen): add b64 + media_type_for helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `extract_svg` — pull the SVG from a model reply

**Files:**
- Create: `src/svgbuilder/enginegen/extract_svg.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.extract_svg import extract_svg


def test_extract_svg_from_code_fence():
    reply = "Here you go:\n```svg\n<svg viewBox=\"0 0 1 1\"><rect/></svg>\n```\nDone."
    assert extract_svg(reply) == '<svg viewBox="0 0 1 1"><rect/></svg>'


def test_extract_svg_from_raw_text():
    reply = '<svg viewBox="0 0 2 2"><circle/></svg>'
    assert extract_svg(reply) == reply


def test_extract_svg_is_case_insensitive_and_multiline():
    reply = "junk\n<SVG\n viewBox=\"0 0 3 3\">\n<g></g>\n</SVG> trailing"
    out = extract_svg(reply)
    assert out.startswith("<SVG") and out.endswith("</SVG>")


def test_extract_svg_missing_raises():
    with pytest.raises(ValueError):
        extract_svg("no svg here")
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k extract_svg -v`
Expected: FAIL with `ImportError: cannot import name 'extract_svg'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/extract_svg.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS (all enginegen tests so far).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/extract_svg.py tests/test_enginegen.py
git commit -m "feat(enginegen): add extract_svg reply parser

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `validate` — convention checks

**Files:**
- Create: `src/svgbuilder/enginegen/validate.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.validate import validate

_GOOD = (
    '<svg viewBox="0 0 200 100">'
    '<circle cx="60" cy="88" r="15" fill="#2c2c2a"/>'
    '<circle cx="120" cy="88" r="15" fill="#2c2c2a"/>'
    '<rect x="0" y="40" width="200" height="40" fill="#1f6b54"/>'
    '</svg>'
)


def test_validate_good_sprite():
    r = validate(_GOOD)
    assert r["has_viewbox"] is True
    assert r["wheel_count"] == 2
    assert r["ok"] is True


def test_validate_flags_missing_wheels():
    svg = '<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="#1f6b54"/></svg>'
    r = validate(svg)
    assert r["wheel_count"] == 0
    assert r["ok"] is False


def test_validate_flags_missing_viewbox():
    svg = _GOOD.replace('viewBox="0 0 200 100"', "")
    r = validate(svg)
    assert r["has_viewbox"] is False
    assert r["ok"] is False


def test_validate_ignores_small_or_wrongcolor_circles():
    svg = (
        '<svg viewBox="0 0 200 100">'
        '<circle cx="60" cy="88" r="2" fill="#2c2c2a"/>'      # too small (hub)
        '<circle cx="120" cy="88" r="15" fill="#d9a834"/>'    # wrong colour
        '</svg>'
    )
    assert validate(svg)["wheel_count"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k validate -v`
Expected: FAIL with `ImportError: cannot import name 'validate'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/validate.py`:
```python
"""Advisory convention checks for a generated engine sprite."""

import re

WHEEL_FILL = "#2c2c2a"
WHEEL_MIN_RADIUS = 6.0

_CIRCLE_RE = re.compile(r"<circle\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')


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
    has_viewbox = 'viewbox="' in svg.lower()
    wheels = [c for c in _circles(svg)
              if c["fill"] == WHEEL_FILL and c["r"] >= WHEEL_MIN_RADIUS]
    return {
        "has_viewbox": has_viewbox,
        "wheel_count": len(wheels),
        "ok": has_viewbox and len(wheels) >= 2,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/validate.py tests/test_enginegen.py
git commit -m "feat(enginegen): add convention validation (wheels + viewBox)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `render` — SVG → PNG bytes

**Files:**
- Create: `src/svgbuilder/enginegen/render.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.render import render_png_bytes


def test_render_png_bytes_returns_png():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10" fill="red"/></svg>'
    data = render_png_bytes(svg)
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:4]) == b"\x89PNG"
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k render -v`
Expected: FAIL with `ImportError: cannot import name 'render_png_bytes'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/render.py`:
```python
"""Render an SVG string to PNG bytes (for the critique loop and previews)."""


def render_png_bytes(svg):
    """Rasterize an SVG string to PNG bytes on a white background, via resvg."""
    import resvg_py

    return bytes(resvg_py.svg_to_bytes(svg_string=svg, background="white"))
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/render.py tests/test_enginegen.py
git commit -m "feat(enginegen): add SVG->PNG render helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `exemplars` — load bundled style data

**Files:**
- Create: `src/svgbuilder/enginegen/exemplars.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.exemplars import load_exemplars, load_conventions


def test_load_exemplars_returns_named_svgs():
    ex = load_exemplars()
    assert len(ex) == 3
    names = [n for n, _ in ex]
    assert "classic-american-4-4-0.svg" in names
    for _name, svg in ex:
        assert "<svg" in svg


def test_load_exemplars_includes_extra_refs(tmp_path):
    ref = tmp_path / "mine.svg"
    ref.write_text('<svg viewBox="0 0 1 1"></svg>')
    ex = load_exemplars(extra_paths=[str(ref)])
    assert ("mine.svg", '<svg viewBox="0 0 1 1"></svg>') in ex
    assert len(ex) == 4


def test_load_conventions_nonempty():
    assert "WHEELS" in load_conventions()
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k "exemplars or conventions" -v`
Expected: FAIL with `ImportError: cannot import name 'load_exemplars'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/exemplars.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/exemplars.py tests/test_enginegen.py
git commit -m "feat(enginegen): add exemplar + conventions loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `generate`/`revise` — the Claude vision calls

**Files:**
- Create: `src/svgbuilder/enginegen/generate.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.generate import make_generator


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text, capture):
        self._text, self._capture = text, capture

    def create(self, **kwargs):
        self._capture.append(kwargs)
        return _Resp(self._text)


class _FakeClient:
    def __init__(self, text, capture):
        self.messages = _FakeMessages(text, capture)


def test_generate_sends_photo_and_returns_text():
    cap = []
    fake = _FakeClient("<svg/>", cap)
    generate, _revise = make_generator(model="claude-opus-4-8", client=fake)
    out = generate("BASE64PHOTO", "image/jpeg",
                   [("ex.svg", "<svg/>")], "CONVENTIONS")
    assert out == "<svg/>"
    content = cap[0]["messages"][0]["content"]
    images = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["source"]["media_type"] == "image/jpeg"
    assert cap[0]["model"] == "claude-opus-4-8"
    assert cap[0]["system"] == "CONVENTIONS"


def test_revise_sends_photo_and_render():
    cap = []
    fake = _FakeClient("<svg2/>", cap)
    _generate, revise = make_generator(model="claude-opus-4-8", client=fake)
    out = revise("PHOTO64", "image/png", "RENDER64", "<svg/>", "CONVENTIONS")
    assert out == "<svg2/>"
    content = cap[0]["messages"][0]["content"]
    images = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(images) == 2  # source photo + current render
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k "generate or revise" -v`
Expected: FAIL with `ImportError: cannot import name 'make_generator'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/generate.py`:
```python
"""Claude vision calls that author and refine an engine sprite SVG."""

DEFAULT_MODEL = "claude-opus-4-8"


def _image_block(b64_data, media_type):
    return {"type": "image", "source": {
        "type": "base64", "media_type": media_type, "data": b64_data}}


def _exemplar_text(exemplars):
    return "\n\n".join(f"<!-- EXAMPLE: {name} -->\n{svg}" for name, svg in exemplars)


def make_generator(model=DEFAULT_MODEL, client=None):
    """Return (generate, revise) callables backed by the Anthropic vision API.

    generate(photo_b64, photo_media, exemplars, conventions) -> reply text
    revise(photo_b64, photo_media, render_b64, current_svg, conventions) -> reply text
    Both return the model's raw text reply (run extract_svg on it). A default
    Anthropic client is created lazily if none is supplied.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    def _ask(content, conventions):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=conventions,
            messages=[{"role": "user", "content": content}],
        )
        return next(b.text for b in response.content if b.type == "text")

    def generate(photo_b64, photo_media, exemplars, conventions):
        return _ask([
            {"type": "text", "text": "House-style example sprites to match:"},
            {"type": "text", "text": _exemplar_text(exemplars)},
            {"type": "text", "text":
                "Draw THIS locomotive in the same house style, resembling it "
                "(livery colors, wheel arrangement, standout features). "
                "Output only the SVG."},
            _image_block(photo_b64, photo_media),
        ], conventions)

    def revise(photo_b64, photo_media, render_b64, current_svg, conventions):
        return _ask([
            {"type": "text", "text": "SOURCE photo of the locomotive:"},
            _image_block(photo_b64, photo_media),
            {"type": "text", "text": "CURRENT rendered sprite from your SVG:"},
            _image_block(render_b64, "image/png"),
            {"type": "text", "text": "Current SVG:\n" + current_svg},
            {"type": "text", "text":
                "Improve the SVG so it better resembles the source and follows all "
                "conventions (facing right; #2c2c2a wheel circles of radius >= 6 "
                "along the lower frame; correct wheel count; house palette). If it "
                "is already good, return it unchanged. Output only the SVG."},
        ], conventions)

    return generate, revise
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/generate.py tests/test_enginegen.py
git commit -m "feat(enginegen): add generate/revise Claude vision calls

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `generate_engine` — the loop

**Files:**
- Create: `src/svgbuilder/enginegen/loop.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen.loop import generate_engine

_SPRITE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
    '<circle cx="60" cy="88" r="15" fill="#2c2c2a"/>'
    '<circle cx="120" cy="88" r="15" fill="#2c2c2a"/>'
    '</svg>'
)


def _photo(tmp_path):
    p = tmp_path / "loco.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # bytes are never decoded (fakes)
    return str(p)


def test_generate_engine_runs_and_validates(tmp_path):
    calls = {"gen": 0, "rev": 0}

    def generate(photo_b64, media, exemplars, conventions):
        calls["gen"] += 1
        return f"```svg\n{_SPRITE}\n```"

    def revise(photo_b64, media, render_b64, current_svg, conventions):
        calls["rev"] += 1
        return _SPRITE  # unchanged -> loop stops

    svg, report = generate_engine(
        _photo(tmp_path), generate=generate, revise=revise,
        render=lambda s: b"\x89PNG", exemplars=[], conventions="C", rounds=3,
    )
    assert "<circle" in svg
    assert report["wheel_count"] == 2 and report["ok"] is True
    assert calls["gen"] == 1
    assert calls["rev"] == 1  # stopped after the first revise returned unchanged


def test_generate_engine_respects_rounds(tmp_path):
    # revise always returns a *different* svg, so it should run rounds-1 times.
    variants = [_SPRITE.replace("200", "201"), _SPRITE.replace("200", "202"),
                _SPRITE.replace("200", "203")]

    def revise(photo_b64, media, render_b64, current_svg, conventions):
        return variants.pop(0)

    svg, report = generate_engine(
        _photo(tmp_path), generate=lambda *a: _SPRITE, revise=revise,
        render=lambda s: b"\x89PNG", exemplars=[], conventions="C", rounds=3,
    )
    # 1 generate + (rounds-1)=2 revises consumed two variants
    assert svg == _SPRITE.replace("200", "202")
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k generate_engine -v`
Expected: FAIL with `ImportError: cannot import name 'generate_engine'`.

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/loop.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/loop.py tests/test_enginegen.py
git commit -m "feat(enginegen): add generate_engine render/revise loop

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: CLI

**Files:**
- Create: `src/svgbuilder/enginegen/cli.py`
- Test: `tests/test_enginegen.py`

- [ ] **Step 1: Append tests to `tests/test_enginegen.py`:**
```python
from svgbuilder.enginegen import cli as engine_cli


def test_cli_missing_input_returns_2(tmp_path):
    assert engine_cli.main([str(tmp_path / "nope.png")]) == 2


def test_cli_end_to_end_with_fake_generator(tmp_path, monkeypatch):
    # Replace the real Anthropic-backed generator with fakes (no network).
    def fake_make_generator(model=None, client=None):
        def generate(photo_b64, media, exemplars, conventions):
            return _SPRITE
        def revise(photo_b64, media, render_b64, current_svg, conventions):
            return _SPRITE
        return generate, revise

    monkeypatch.setattr(engine_cli, "make_generator", fake_make_generator)

    src = tmp_path / "loco.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    out = tmp_path / "engine.svg"
    code = engine_cli.main([str(src), "-o", str(out), "--rounds", "2", "--quiet"])
    assert code == 0
    assert out.exists() and "<circle" in out.read_text()
    assert (tmp_path / "engine.preview.png").exists()


def test_cli_reports_setup_error_when_generator_unavailable(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("no api key")
    monkeypatch.setattr(engine_cli, "make_generator", boom)
    src = tmp_path / "loco.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    code = engine_cli.main([str(src), "--quiet"])
    assert code == 1
    assert "no api key" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -k cli -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.enginegen.cli'` (or AttributeError on `main`).

- [ ] **Step 3: Write minimal implementation** — `src/svgbuilder/enginegen/cli.py`:
```python
"""Command-line interface for the engine-sprite generator."""

import argparse
import os
import sys

from .. import __version__
from .exemplars import load_conventions, load_exemplars
from .generate import DEFAULT_MODEL, make_generator
from .loop import generate_engine
from .render import render_png_bytes


def derive_output_path(input_path, output):
    if output:
        return output
    base, _ = os.path.splitext(input_path)
    return base + ".svg"


def _build_parser():
    p = argparse.ArgumentParser(
        prog="enginegen",
        description="Generate a clean house-style engine sprite SVG from a photo.",
        epilog="Example: enginegen loco.jpg -o my-engine.svg --rounds 3",
    )
    p.add_argument("input", help="Path to the locomotive photo (jpg/png/webp).")
    p.add_argument("-o", "--output", help="Output .svg path (default: alongside input).")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Claude model (default {DEFAULT_MODEL}).")
    p.add_argument("--rounds", type=int, default=3,
                   help="Generate + revise rounds (default 3).")
    p.add_argument("--style-ref", action="append", default=None, dest="style_ref",
                   metavar="FILE", help="Extra house-style SVG to bias toward (repeatable).")
    p.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    p.add_argument("--version", action="version", version=f"enginegen {__version__}")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    try:
        exemplars = load_exemplars(extra_paths=args.style_ref)
        conventions = load_conventions()
        generate, revise = make_generator(model=args.model)
        svg, report = generate_engine(
            args.input, generate=generate, revise=revise,
            render=render_png_bytes, exemplars=exemplars,
            conventions=conventions, rounds=args.rounds,
        )
    except Exception as exc:  # missing key, no <svg>, API error, etc.
        print(f"error: generation failed: {exc}\n"
              "hint: enginegen needs the [engine] extra and an ANTHROPIC_API_KEY "
              "(pip install 'svgbuilder[engine]').", file=sys.stderr)
        return 1

    out_path = derive_output_path(args.input, args.output)
    try:
        with open(out_path, "w") as fh:
            fh.write(svg)
        preview_path = os.path.splitext(out_path)[0] + ".preview.png"
        with open(preview_path, "wb") as fh:
            fh.write(render_png_bytes(svg))
    except OSError as exc:
        print(f"error: could not write output: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        note = "" if report["ok"] else "  [warning: no wheels detected — extract_assets may miss them]"
        print(f"wrote {out_path}  (wheels={report['wheel_count']}, "
              f"rounds={args.rounds}){note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the cli tests, then the full suite**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_enginegen.py -v`
Expected: PASS (all enginegen tests).

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q`
Expected: all project tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/enginegen/cli.py tests/test_enginegen.py
git commit -m "feat(enginegen): add CLI with preview output and setup-error handling

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: README + manual real generation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `enginegen` in the README**

In `README.md`, add a top-level section before `## License`:
```markdown
## enginegen — photo → designed engine sprite

`enginegen` is a separate command that *generates* a clean, hand-drawn-style
locomotive SVG resembling an input photo — for use as a game sprite — rather than
tracing the photo's pixels. It uses a Claude vision model (default
`claude-opus-4-8`) to author the SVG in a fixed house style, refining it over a
few render→critique→revise rounds.

    pip install 'svgbuilder[engine]'
    export ANTHROPIC_API_KEY=sk-ant-...
    enginegen loco.jpg -o my-engine.svg --rounds 3

Output: a `.svg` (+ a `.preview.png`). It bundles a few house-style exemplars;
add `--style-ref FILE` to bias toward a closest match. Requires an API key (the
model is the tool — there is no offline fallback).
```

- [ ] **Step 2: Manual real generation (requires a key)**

Run (only if `ANTHROPIC_API_KEY` is set):
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
.venv/bin/enginegen "/Users/nitzanwilnai/Downloads/TrainGame/Engines/4-4-0 American 4.jpg" \
  -o /tmp/gen_4_4_0.svg --rounds 3
ls -l /tmp/gen_4_4_0.svg /tmp/gen_4_4_0.preview.png
```
Expected (with a key): exits 0, prints `wrote ... (wheels=N, rounds=3)`, and writes both files. Open the preview PNG to eyeball that it resembles the engine in the house style with distinct wheels. If no key is set, skip this step and note it — the unit suite already covers the logic with fakes.

- [ ] **Step 3: Final full-suite run + help check**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q && .venv/bin/enginegen --help | head -5`
Expected: all tests pass and `enginegen --help` prints usage.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the enginegen photo->sprite generator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes
- **Non-deterministic** (generative). The revise loop + your visual review are the quality mechanism; `validate` is advisory (it warns, never blocks).
- **The live API is not unit-tested** (needs a key + spend); the calls are isolated in `generate.py` and verified with a fake client, and the CLI is covered end-to-end with an injected fake generator. Exercise the real path manually (Task 10 Step 2).
- **Integration:** the generated sprite faces right (treat as `NO_MIRROR`); drop it into `TrainGame/src/assets/engines/` and run `extract_assets.js` to refresh `manifest.json`. `enginegen` deliberately does none of that.
