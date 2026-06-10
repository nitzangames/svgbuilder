# svgbuilder Stage 3 (`--llm-refine` LLM-steered tuning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `--llm-refine` mode where a Claude vision model compares the source image to the current vector render and returns a constrained JSON parameter-delta to steer the tuning loop — never emitting SVG — with a hard fallback to the deterministic Stage-2 loop when the API key or `[llm]` extra is absent.

**Architecture:** A new `llm_refine.py` module owns (1) `apply_suggestion` — a pure function that merges a validated JSON delta into the current params, (2) `make_suggester` — the thin Anthropic vision call that returns a parsed delta dict, and (3) `llm_refine_vectorize` — a keep-best loop that takes an injected `suggest` callable (so it's testable without the network). The CLI's `--llm-refine` builds a real suggester and runs the loop, catching any error/missing-key and falling back to `auto_vectorize`. The LLM only ever proposes parameter values from a fixed enum; it never touches SVG.

**Tech Stack:** Python 3.10–3.13 (project `.venv` = Python 3.12), the `anthropic` SDK (model default `claude-opus-4-8`), reusing Stage 2's `render_svg`/`score`/`vectorize`/`quantize`.

**Environment note:** Run everything with `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python` (Python 3.12). Never use bare `python3` (system 3.14 has a broken vtracer wheel). Tests run from the project root, so `tests/fixtures/sample.png` resolves. No `ANTHROPIC_API_KEY` is required to run the tests — the LLM call is dependency-injected/faked, and the CLI fallback path is what runs without a key.

---

## File Structure

- Modify: `pyproject.toml` — add `[llm]` optional-dependency group (`anthropic`).
- Create: `src/svgbuilder/llm_refine.py` — `apply_suggestion`, `make_suggester`, `llm_refine_vectorize`.
- Modify: `src/svgbuilder/cli.py` — add `--llm-refine` / `--llm-model`, wire to `llm_refine_vectorize` with graceful fallback to `auto_vectorize`.
- Create: `tests/test_llm_refine.py` — unit tests for `apply_suggestion`, `llm_refine_vectorize` (fake suggester), and `make_suggester` (fake client).
- Modify: `tests/test_cli.py` — add an end-to-end `--llm-refine` test that exercises the no-key fallback.
- Modify: `README.md` — document `--llm-refine` and the `[llm]` extra.

`llm_refine_vectorize` reuses Stage 2's `render_svg`, `score`, plus `preprocess.quantize` and `vectorize.vectorize` — it does not duplicate them.

---

### Task 1: Add the `[llm]` optional-dependency extra

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the `llm` extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, add an `llm` group after the existing `auto` group:
```toml
llm = [
    "anthropic>=0.40",
]
```
(Leave `dev` and `auto` unchanged.)

- [ ] **Step 2: Install with all extras**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
.venv/bin/python -m pip install -e ".[auto,llm,dev]"
```
Verify:
```bash
.venv/bin/python -c "import anthropic; print('anthropic', anthropic.__version__)"
```
Expected: prints a version. If `anthropic>=0.40` cannot be satisfied, check `.venv/bin/python -m pip index versions anthropic` and lower the floor to an available version, noting the change. If install fails otherwise, STOP and report BLOCKED.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add [llm] optional-dependency extra (anthropic)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `apply_suggestion` — validate and merge a JSON delta

**Files:**
- Create: `src/svgbuilder/llm_refine.py`
- Test: `tests/test_llm_refine.py`

- [ ] **Step 1: Write the failing test**

`tests/test_llm_refine.py`:
```python
from svgbuilder.llm_refine import apply_suggestion
from svgbuilder.presets import get_preset


def test_apply_suggestion_applies_valid_values():
    base = get_preset("clean")
    out = apply_suggestion(base, {"color_precision": 3, "mode": "polygon"})
    assert out["color_precision"] == 3
    assert out["mode"] == "polygon"


def test_apply_suggestion_ignores_out_of_range_and_unknown_keys():
    base = get_preset("clean")
    out = apply_suggestion(base, {"color_precision": 999, "colors": 4, "bogus": 1})
    assert out["color_precision"] == base["color_precision"]  # 999 not allowed
    assert out["colors"] == base["colors"]                    # colors not tunable here
    assert "bogus" not in out


def test_apply_suggestion_returns_a_copy():
    base = get_preset("clean")
    out = apply_suggestion(base, {"filter_speckle": 8})
    out["filter_speckle"] = -1
    assert get_preset("clean")["filter_speckle"] == base["filter_speckle"]
    assert base["filter_speckle"] != -1


def test_apply_suggestion_ignores_done_and_non_param_fields():
    base = get_preset("clean")
    out = apply_suggestion(base, {"done": True, "corner_threshold": 40})
    assert "done" not in out
    assert out["corner_threshold"] == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'svgbuilder.llm_refine'`.

- [ ] **Step 3: Write minimal implementation**

`src/svgbuilder/llm_refine.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/llm_refine.py tests/test_llm_refine.py
git commit -m "feat: add apply_suggestion param-delta validator for LLM refine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `llm_refine_vectorize` — the keep-best loop (injected suggester)

**Files:**
- Modify: `src/svgbuilder/llm_refine.py`
- Test: `tests/test_llm_refine.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_llm_refine.py`)**

```python
from svgbuilder.llm_refine import llm_refine_vectorize
from svgbuilder.preprocess import load_image

_FIXTURE = "tests/fixtures/sample.png"


def test_llm_refine_returns_svg_and_respects_budget():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    calls = {"n": 0}

    def suggest(source_rgb, candidate_rgb, current_params):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"done": False, "filter_speckle": 8}
        return {"done": True}

    svg, params, best, evals = llm_refine_vectorize(
        src, get_preset("clean"), smooth=False, budget=5, suggest=suggest
    )
    assert "<path" in svg
    assert 1 <= evals <= 5
    assert -1.0 <= best <= 1.0
    assert isinstance(params, dict)


def test_llm_refine_stops_on_done():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    def suggest(source_rgb, candidate_rgb, current_params):
        return {"done": True}

    svg, params, best, evals = llm_refine_vectorize(
        src, get_preset("clean"), smooth=False, budget=5, suggest=suggest
    )
    assert evals == 1  # baseline only; suggester immediately said done


def test_llm_refine_propagates_first_call_error():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")

    def suggest(source_rgb, candidate_rgb, current_params):
        raise RuntimeError("no api key")

    import pytest
    with pytest.raises(RuntimeError):
        llm_refine_vectorize(src, get_preset("clean"), smooth=False, budget=5, suggest=suggest)


def test_llm_refine_never_worse_than_baseline():
    src = load_image(_FIXTURE, max_size=1000, bg="auto")
    base = get_preset("clean")

    from svgbuilder.autotune import render_svg, score
    from svgbuilder.preprocess import quantize
    from svgbuilder.vectorize import vectorize
    src_rgb = src.convert("RGB")
    base_svg = vectorize(quantize(src, colors=base["colors"], smooth=False), base)
    base_score = score(render_svg(base_svg, src.size), src_rgb)

    def suggest(source_rgb, candidate_rgb, current_params):
        # propose a likely-worse extreme, then stop
        return {"done": True} if current_params.get("color_precision") == 2 else {"color_precision": 2}

    _svg, _params, best, _evals = llm_refine_vectorize(
        src, base, smooth=False, budget=4, suggest=suggest
    )
    assert best >= base_score - 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -k llm_refine -v`
Expected: FAIL with `ImportError: cannot import name 'llm_refine_vectorize'`.

- [ ] **Step 3: Add the implementation to `src/svgbuilder/llm_refine.py`**

Append after `apply_suggestion`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -v`
Expected: PASS (all `apply_suggestion` + `llm_refine` tests green).

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/llm_refine.py tests/test_llm_refine.py
git commit -m "feat: add llm_refine_vectorize keep-best loop with injected suggester

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `make_suggester` — the Claude vision call

**Files:**
- Modify: `src/svgbuilder/llm_refine.py`
- Test: `tests/test_llm_refine.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_llm_refine.py`)**

```python
import json as _json
from PIL import Image as _Image
from svgbuilder.llm_refine import make_suggester


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text, capture):
        self._text = text
        self._capture = capture

    def create(self, **kwargs):
        self._capture.update(kwargs)
        return _Resp(self._text)


class _FakeClient:
    def __init__(self, text, capture):
        self.messages = _FakeMessages(text, capture)


def test_make_suggester_sends_two_images_and_parses_json():
    capture = {}
    fake = _FakeClient(_json.dumps({"done": False, "color_precision": 3}), capture)
    suggest = make_suggester(model="claude-opus-4-8", client=fake)

    src = _Image.new("RGB", (16, 16), (10, 120, 70))
    cand = _Image.new("RGB", (16, 16), (10, 120, 70))
    result = suggest(src, cand, {"color_precision": 4, "filter_speckle": 6,
                                 "corner_threshold": 60, "mode": "spline"})

    assert result == {"done": False, "color_precision": 3}
    # two image blocks were sent to the model
    content = capture["messages"][0]["content"]
    image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(image_blocks) == 2
    assert capture["model"] == "claude-opus-4-8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -k make_suggester -v`
Expected: FAIL with `ImportError: cannot import name 'make_suggester'`.

- [ ] **Step 3: Add the implementation to `src/svgbuilder/llm_refine.py`**

Add these constants after the `ALLOWED` dict near the top of the file:
```python
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
```

Then append this function at the end of the file:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_llm_refine.py -v`
Expected: PASS (all llm_refine tests). Note: the real network call is exercised only by the fake client here; a live key is not needed.

- [ ] **Step 5: Commit**

```bash
git add src/svgbuilder/llm_refine.py tests/test_llm_refine.py
git commit -m "feat: add make_suggester Claude vision call for LLM refine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire `--llm-refine` into the CLI (with fallback)

**Files:**
- Modify: `src/svgbuilder/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_cli.py`)**

```python
def test_main_llm_refine_falls_back_when_suggester_unavailable(tmp_path, monkeypatch, capsys):
    # Force the LLM path to fail deterministically (no network): make_suggester
    # raises, simulating a missing key / unavailable API. The CLI must catch it,
    # print a fallback warning, run the deterministic loop, and still write SVG.
    import svgbuilder.llm_refine as llm_refine

    def boom(*args, **kwargs):
        raise RuntimeError("no api key")

    monkeypatch.setattr(llm_refine, "make_suggester", boom)

    out = tmp_path / "llm.svg"
    exit_code = main([
        "tests/fixtures/sample.png", "-o", str(out),
        "--llm-refine", "--auto-budget", "3", "--no-smooth",
    ])
    assert exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "<svg" in text and "<path" in text
    err = capsys.readouterr().err
    assert "fall" in err.lower() or "deterministic" in err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_cli.py::test_main_llm_refine_falls_back_when_suggester_unavailable -v`
Expected: FAIL — `--llm-refine` is not yet a recognized argument (SystemExit), or the fallback message is absent.

- [ ] **Step 3: Add the flags to `_build_parser()`**

In `src/svgbuilder/cli.py`, add these two arguments immediately AFTER the `--auto-budget` argument (and before `--quiet`):
```python
    p.add_argument("--llm-refine", action="store_true", dest="llm_refine",
                   help="Use a Claude vision model to steer auto-tuning (needs the "
                        "[auto] and [llm] extras + an API key). Falls back to --auto "
                        "if unavailable.")
    p.add_argument("--llm-model", default="claude-opus-4-8", dest="llm_model",
                   help="Claude model for --llm-refine (default claude-opus-4-8).")
```

- [ ] **Step 4: Route `--llm-refine` through the loop in `main`**

In `src/svgbuilder/cli.py`, the `if args.auto:` branch added in Stage 2 currently reads:
```python
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
```
Replace that entire `if args.auto:` block (up to but NOT including the `else:`) with:
```python
        if args.auto or args.llm_refine:
            try:
                from .autotune import auto_vectorize
            except ImportError:
                print("error: --auto/--llm-refine need the [auto] extra. Install it "
                      "with: pip install 'svgbuilder[auto]'", file=sys.stderr)
                return 1

            smooth = not args.no_smooth
            if args.llm_refine:
                try:
                    from .llm_refine import llm_refine_vectorize, make_suggester
                    suggest = make_suggester(model=args.llm_model)
                    svg, params, best_score, evals = llm_refine_vectorize(
                        img, params, smooth=smooth, budget=args.auto_budget, suggest=suggest
                    )
                    auto_info = f"llm-refine: score={best_score:.3f} in {evals} evals"
                except Exception as exc:
                    print(f"warning: --llm-refine unavailable ({exc}); falling back to "
                          "deterministic auto-tuning.", file=sys.stderr)
                    svg, params, best_score, evals = auto_vectorize(
                        img, params, smooth=smooth, budget=args.auto_budget
                    )
                    auto_info = f"auto (llm fallback): score={best_score:.3f} in {evals} evals"
            else:
                svg, params, best_score, evals = auto_vectorize(
                    img, params, smooth=smooth, budget=args.auto_budget
                )
                auto_info = f"auto: score={best_score:.3f} in {evals} evals"
        else:
```
(The trailing `else:` and its single-trace body stay exactly as they were.)

- [ ] **Step 5: Run the CLI test, then the full suite**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS (Stage 1+2 cli tests plus the new fallback test).

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/svgbuilder/cli.py tests/test_cli.py
git commit -m "feat: add --llm-refine to the CLI with deterministic fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: README, fallback smoke test, final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `--llm-refine` in the README**

In `README.md`, add these two bullets to the Options list, immediately after the `--auto-budget` bullet:
```markdown
- `--llm-refine`          steer tuning with a Claude vision model (needs `[auto]`+`[llm]` + API key)
- `--llm-model NAME`      Claude model for `--llm-refine` (default `claude-opus-4-8`)
```
Then add this section immediately after the existing "Auto-tuning (`--auto`)" section:
```markdown
### LLM-steered tuning (`--llm-refine`)

With the `[auto]` and `[llm]` extras installed and an `ANTHROPIC_API_KEY` set,
`--llm-refine` lets a Claude vision model look at the source and the current
render and suggest parameter changes (it never writes SVG itself):

    pip install 'svgbuilder[auto,llm]'
    export ANTHROPIC_API_KEY=sk-ant-...
    svgbuilder train.jpg --auto-budget 6 --llm-refine
    svgbuilder train.jpg --llm-refine --llm-model claude-haiku-4-5

If the extras or key are missing, it prints a warning and falls back to the
deterministic `--auto` loop — so the command always produces an SVG.
```

- [ ] **Step 2: Fallback smoke test on a real image (no key required)**

Run:
```bash
cd /Users/nitzanwilnai/Programming/Claude/SVGBuilder
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  .venv/bin/svgbuilder "/Users/nitzanwilnai/Downloads/TrainGame/Engines/4-4-0 American 4.jpg" \
  -o /tmp/eng_llm.svg --llm-refine --auto-budget 4
ls -l /tmp/eng_llm.svg
```
Expected: exits 0, prints a `warning: --llm-refine unavailable (...); falling back` line to stderr and a `wrote ... [auto (llm fallback): ...]` line, and writes a valid SVG. (If a real `ANTHROPIC_API_KEY` happens to be set in the environment, instead expect a `[llm-refine: ...]` success line — either outcome is acceptable; the point is exit 0 + valid SVG.)

- [ ] **Step 3: Final full-suite run + help check**

Run: `/Users/nitzanwilnai/Programming/Claude/SVGBuilder/.venv/bin/python -m pytest -q && .venv/bin/svgbuilder --help | grep -E "llm-refine|llm-model"`
Expected: all tests pass and `--help` lists `--llm-refine` and `--llm-model`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document --llm-refine LLM-steered tuning

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes
- **The LLM only proposes parameters from `ALLOWED`** (validated by `apply_suggestion` *and* constrained by the JSON schema) — it never emits or edits SVG, matching the research conclusion that LLM-authored SVG hurts fidelity on complex art.
- **Determinism caveat:** unlike Stages 1–2, `--llm-refine` is non-deterministic (the model may suggest different deltas across runs). The keep-best guarantee still holds — the result is never worse than the Stage-1 baseline trace.
- **Default model is `claude-opus-4-8`** per Anthropic guidance; use `--llm-model claude-haiku-4-5` (or `claude-sonnet-4-6`) for a cheaper/faster loop.
- **Live API is not unit-tested** (needs a key + spend); the network call is isolated in `make_suggester` and verified via a fake client, while the real path is protected by the CLI fallback. A manual `ANTHROPIC_API_KEY=... svgbuilder <img> --llm-refine` run is the way to exercise it end-to-end.
