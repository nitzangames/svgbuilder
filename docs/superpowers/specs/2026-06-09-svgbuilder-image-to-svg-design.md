# svgbuilder — Image → SVG Vectorizer (Design)

**Date:** 2026-06-09
**Status:** Approved (pending spec review)

## 1. Overview

`svgbuilder` is an installable Python CLI that converts a single raster image
(jpg/webp/png) into a clean, simplified, colored SVG. It is designed to be
open-sourced and to be invoked reliably by other Claude Code agents — one image
per run, predictable flags, clear exit codes, thorough `--help`.

The core is a deterministic tracing pipeline. An optional, layered critic loop
auto-tunes parameters for higher quality, and an optional LLM step can steer that
loop. The base tool works fully offline with no API key.

### Goals
- Clean / simplified colored SVG output (default ~16 colors), tunable.
- One image at a time; scriptable by humans and agents.
- Deterministic and reliable by default; smart enhancements strictly opt-in.
- Installable and distributable as a conventional open-source Python package.

### Non-goals
- Batch/folder processing (single image per run by design).
- LLM-authored SVG markup (research shows this loses fidelity on complex art).
- Photographic-fidelity tracing (we target a clean illustrated look).

## 2. Architecture

Pipeline:

```
input image
  → load (Pillow, RGBA)
  → preprocess (optional downscale + denoise + palette quantization)
  → vectorize (VTracer, spline mode, preset/auto-tuned params)
  → write .svg
```

Optional layers wrap the vectorize step:

- `--auto`  : deterministic critic loop (render → score → adjust knobs → keep best).
- `--llm-refine` : LLM vision critic suggests parameter deltas to steer `--auto`.

### Module layout (each file one job)
- `svgbuilder/cli.py` — argparse, help text, orchestration, exit codes, stats output.
- `svgbuilder/preprocess.py` — load image, optional downscale, denoise, palette quantization.
- `svgbuilder/vectorize.py` — VTracer invocation and parameter mapping.
- `svgbuilder/presets.py` — named presets → parameter dicts.
- `svgbuilder/autotune.py` — Stage 2 deterministic critic loop (render, score, search).
- `svgbuilder/llm_refine.py` — Stage 3 optional LLM parameter suggester.
- `pyproject.toml`, `README.md`, `LICENSE` (MIT), `tests/`.

## 3. Stage 1 — Core (V1, ships first)

### Data flow
1. **Load** with Pillow → `RGBA`. JPEG/WebP/PNG supported. If the source has no
   alpha it stays opaque; if it has alpha, transparency is preserved by default
   (good for game sprites). `--bg white|none|auto` overrides flattening behavior.
2. **Preprocess (the "clean" magic):**
   - Downscale if the longest edge exceeds `--max-size` (default 1000 px) — fewer
     JPEG-noise speckles, cleaner regions, faster tracing.
   - Optional light median-filter denoise (`--no-smooth` to disable).
   - **Palette quantization** via Pillow:
     `img.convert('RGBA').quantize(colors=N, method=Image.Quantize.FASTOCTREE,
     dither=Image.Dither.NONE).convert('RGBA')`.
     FASTOCTREE is chosen because it handles RGBA, is deterministic (no RNG), and
     is fast. Dithering is disabled — it creates speckle that fights the tracer.
3. **Vectorize** with VTracer in `spline` (smooth) mode using preset params, via
   `vtracer.convert_pixels_to_svg(pixels, size, **params)` (pixel API gives the
   most control over the pre-quantized palette).
4. **Write** SVG to `-o PATH`, or default to `<input_stem>.svg` next to the input.

### Presets (concrete VTracer params)

| Preset | colors | color_precision | filter_speckle | layer_difference | corner_threshold | length_threshold | splice_threshold | mode |
|---|---|---|---|---|---|---|---|---|
| `flat`     | 8  | 3 | 8 | 32 | 70 | 6.0 | 60 | spline |
| `clean` *(default)* | 16 | 4 | 6 | 24 | 60 | 4.0 | 45 | spline |
| `detailed` | 24 | 5 | 4 | 16 | 50 | 4.0 | 45 | spline |

`hierarchical='stacked'`, `path_precision=8`, `max_iterations=10` for all presets.
The `colors` value drives the Pillow pre-quantization; `color_precision` is set
slightly above so VTracer does not re-split the locked palette. Any explicit flag
(`--colors`, `--filter-speckle`, etc.) overrides the preset value.

### CLI

```
svgbuilder INPUT [-o OUT] [--preset clean|flat|detailed]
           [--colors N] [--max-size PX] [--no-smooth] [--bg auto|white|none]
           [--auto] [--llm-refine] [--quiet]
```

- On success prints the output path and stats (colors, path count, byte size)
  unless `--quiet`. Exit 0 on success; non-zero with a clear stderr message on
  failure. Output is deterministic for a given input + flags.
- `--help` documents every flag with examples, so agents can use it without guessing.

### Dependencies & packaging
- Base: `vtracer` (>=0.6.15, prebuilt cp314 wheels confirmed on PyPI incl. macOS
  arm64), `pillow`.
- Optional extras: `[auto]` adds the renderer + `scikit-image`; `[perceptual]`
  adds `dreamsim` (+torch); `[llm]` adds the Anthropic SDK.
- `pyproject.toml` (PEP 621) with a console entry point
  `svgbuilder = "svgbuilder.cli:main"`. Install via `pipx install svgbuilder`
  or `pip install .`. MIT license. README with install, usage, and a worked
  locomotive example.

## 4. Stage 2 — `--auto` deterministic critic loop (no LLM)

Goal: squeeze better quality out of VTracer without any network or LLM.

Loop:
```
candidate = trace(params)
render candidate to raster (resvg; fall back to cairosvg)
score = compare(render, source)
adjust params via coordinate descent over the key knobs
keep the best-scoring candidate seen
```

- **Knobs searched:** `color_precision`, `filter_speckle`, `corner_threshold`,
  and `mode` (spline vs polygon). Coordinate descent, not full grid.
- **Budget:** 3–5 evaluations max (diminishing returns beyond that).
- **Scoring:** SSIM (scikit-image) as a cheap structural gate by default;
  optional perceptual **DreamSim** (`[perceptual]` extra) for semantic similarity
  ("does it still read as the same locomotive"). Never optimize SSIM alone as the
  sole objective — it can disagree with visual quality on vectorized output.
- **Stop when:** score below an absolute threshold, OR relative improvement < ~2%
  for an iteration (plateau), OR budget exhausted. Always return the best
  candidate seen — never a regression.
- **Rendering:** prefer `resvg` (spec-accurate, reproducible); fall back to
  `cairosvg` if resvg is unavailable, with a logged note.

## 5. Stage 3 — `--llm-refine` (optional, off by default)

An LLM vision critic compares the source image and the current rendered candidate
and returns a **constrained JSON parameter-delta** (e.g.
`{"color_precision": +1, "filter_speckle": -2, "note": "lost the gold trim"}`) to
seed or steer the Stage-2 search.

- The LLM **never** emits or edits SVG markup — only parameter suggestions.
- 3–5 iterations, monotonic keep-best, same scoring as Stage 2.
- Uses Claude (Anthropic SDK); ~$0.02/call, ~$0.10–0.15/image for a full loop.
- **Hard fallback:** if no API key or the call errors, silently degrade to the
  Stage-2 deterministic search. The tool never *requires* an API key.

## 6. Error handling

Friendly, actionable messages (not stack traces) for:
- Missing or unreadable input file; unsupported format.
- `vtracer` not importable → message with the exact install command.
- Unwritable output path.
- Optional-feature deps missing when `--auto`/`--llm-refine`/`[perceptual]` is
  requested → message naming the extra to install.

## 7. Testing (TDD)

- **Unit:** preset → param mapping; output-path derivation; quantization actually
  reduces the distinct-color count; `--colors` overrides preset.
- **End-to-end:** trace a tiny synthetic image → assert the result is valid,
  non-empty SVG XML with at least one `<path>`.
- **Stage 2 (when built):** scoring is monotonic (returned candidate score ≥
  starting candidate score); loop respects the eval budget.
- **Manual fixtures:** the locomotive images in `~/Downloads/TrainGame/Engines/`
  serve as visual sanity checks across presets.

## 8. Build order

1. Stage 1 core + packaging + tests (the shippable deliverable).
2. Stage 2 `--auto` deterministic loop.
3. Stage 3 `--llm-refine` optional LLM steering.

## 9. Key research findings (basis for this design)

- VTracer 0.6.15 publishes prebuilt CPython 3.14 wheels, but during
  implementation that wheel was found to **segfault whenever any tuning
  parameter is passed** (pyo3/Python 3.14 bug). Parameter passing works
  correctly on Python 3.10–3.13, so the tool requires `>=3.10,<3.14` and runs
  in a Python 3.12 venv. Revisit once vtracer ships a fixed cp314 wheel.
- Pillow `FASTOCTREE`, dither off, is the right deterministic RGBA pre-quantizer.
- LLM-authored SVG is unreliable for complex/detailed art (SVGenius, LLM4SVG,
  StarVector all converge on this) — so the critic loop tunes parameters, and a
  deterministic search captures most of the gain with zero cost. The LLM is a
  parameter suggester only, and optional.
- Render with `resvg` (spec-accurate, reproducible) over cairosvg for the loop;
  score with an SSIM gate plus optional DreamSim perceptual selection.
