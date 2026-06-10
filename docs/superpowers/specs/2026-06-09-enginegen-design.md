# enginegen — Photo → House-Style Engine Sprite (Design)

**Date:** 2026-06-09
**Status:** Approved (pending spec review)

## 1. Overview

`enginegen` is a new command in the SVGBuilder repo, **separate from the raster
tracer**. Given one photo of a locomotive, a Claude vision model *authors* a
clean, hand-drawn-style SVG sprite that resembles that specific engine — in the
house style of the TrainGame engine assets — refines it through a
render→critique→revise loop, and writes a `.svg`.

This is a **generation** tool, not a tracer. The tracer (`svgbuilder`)
reproduces a photo's pixels as vector regions; `enginegen` produces a designed
illustration in a fixed house vocabulary (flat primitive shapes, side profile,
house palette) that *resembles* the engine but is not a trace.

The output is a single `.svg` file. The user drops it into
`TrainGame/src/assets/engines/` and runs the game's existing `extract_assets.js`,
which auto-derives the wheel metadata (`wheels[]`, `baseline_y`, natural size)
from the SVG. `enginegen` never touches the game repo.

### Goals
- One photo → one house-style engine sprite that resembles the specific engine
  (livery colors, wheel arrangement, steam/diesel, standout features).
- Output conforms to TrainGame conventions so `extract_assets.js` works
  unchanged (wheels are detectable `#2c2c2a` circles in the lower region).
- Reuse SVGBuilder's existing LLM plumbing (`anthropic`) and renderer (`resvg`).

### Non-goals
- Faithful pixel reproduction (that's the tracer).
- Batch/folder processing (one image per run).
- Writing into the game repo or running `extract_assets.js` (the user does that).
- Generating the wheel/baseline metadata directly (the game's extractor derives it).

## 2. Architecture

Pipeline:
```
photo
  → generate(photo + style exemplars + conventions)        -> svg
  → [ render(svg) -> revise(photo + render + svg) ] × rounds -> svg
  → validate(svg)  (warn if no wheels found)
  → write <name>.svg  (+ <name>.preview.png)
```

A focused `enginegen/` subpackage, isolated from the tracer modules:

- `src/svgbuilder/enginegen/__init__.py`
- `src/svgbuilder/enginegen/exemplars.py` — load bundled house-style reference
  SVGs + the conventions text; resolve extra `--style-ref` files.
- `src/svgbuilder/enginegen/extract_svg.py` — pull `<svg>…</svg>` from a model
  reply (strip ``` fences / surrounding prose).
- `src/svgbuilder/enginegen/validate.py` — convention checks on an SVG string.
- `src/svgbuilder/enginegen/render.py` — SVG→PNG bytes via `resvg`.
- `src/svgbuilder/enginegen/generate.py` — `make_generator(model, client)` →
  `generate(photo_b64, exemplars, conventions)` and `revise(photo_b64,
  render_b64, current_svg, conventions)`; both mockable via an injected client.
- `src/svgbuilder/enginegen/loop.py` — `generate_engine(...)` orchestrates rounds.
- `src/svgbuilder/enginegen/cli.py` — argparse, orchestration, exit codes.
- `src/svgbuilder/enginegen/style/*.svg` — bundled exemplar sprites + conventions.
- `pyproject.toml` — new `[engine]` extra and an `enginegen` console script.

## 3. Components & data flow

### Exemplars
Bundle a small curated set of the user's own engine SVGs as the house-style
vocabulary, copied into `enginegen/style/`:
- a steam 4-4-0 (`classic-american-4-4-0.svg`),
- a diesel road-switcher (`cn-gp9-chopnose.svg`),
- a tank engine (`saddle-tank-blue.svg`).

These are passed to the model as text few-shot examples so it has the house
construction patterns (wheels-first layering, palette, comments, viewBox scale).
`--style-ref FILE` adds or biases toward a specific closest-match asset.

### Conventions (hard constraints, in the system prompt)
- Output **only** a single self-contained `<svg>` with a `viewBox` (no prose).
- **Side profile, facing right** (matches the user's newest assets, which are in
  `NO_MIRROR`).
- **Wheels drawn first** (body overlaps their tops), each a `#2c2c2a` circle with
  a steel-tire ring (`#cfcdc3`) and hub, spokes for drivers — like the 4-4-0
  exemplar. Correct **count** for the prototype (4-4-0, 2-8-0, B-B diesel…),
  positioned along the lower frame near the baseline, radius large enough to be
  detected as wheels (the game's `extract_assets.js` requires `#2c2c2a` circles
  of sufficient radius in the bottom ~40%).
- **House palette:** flat fills + darker strokes; gold trim (`#d9a834`/`#f4c775`)
  and steel (`#cfcdc3`) and charcoals (`#191919`/`#2c2c2a`/`#0e0e0e`) for steam;
  match the **photo's livery colors** for the body (e.g. green + gold for a B&O).
- **Layered primitive shapes** (`rect`/`circle`/`line`/`path` with Q/C curves)
  with per-part comments, at a viewBox scale comparable to the exemplars
  (~150–215 units wide).
- **Resemble the specific engine:** capture its standout features (balloon stack,
  saddle tank, streamlining, cowcatcher, domes) and overall proportions.

### The revise call
Sends the source photo + the **rendered** current sprite (PNG) + the current SVG
text, and asks for a corrected SVG that better resembles the engine and fixes any
convention violations, or signals it's already good. This render-in-the-loop step
is what catches geometry/style/resemblance errors a one-shot misses. Markup
rewriting is safe here because the sprites are small primitive-shape SVGs.

### Loop
`generate_engine(photo_path, generate, revise, render, validate, rounds=3)`:
1. Load photo → base64.
2. `svg = generate(photo_b64, ...)`; `svg = extract_svg(reply)`.
3. Repeat up to `rounds-1` times: `png = render(svg)`; `revised = revise(...)`;
   `svg2 = extract_svg(revised)`; stop if the model signals "good" or the SVG is
   unchanged; else `svg = svg2`.
4. Return the final `svg` and a validation report.

No automatic keep-best score: the output is a stylized redraw, so similarity-to-
photo metrics (SSIM) are not meaningful. The revise loop plus user review is the
quality mechanism. `validate` is advisory (warn, don't fail, if wheels missing).

## 4. CLI

```
enginegen INPUT [-o OUT.svg] [--name NAME] [--model claude-opus-4-8]
          [--rounds 3] [--style-ref FILE ...] [--quiet]
```

- Default output: `<input_stem>.svg`, plus `<input_stem>.preview.png` for a quick
  eyeball.
- On success prints the output path, number of wheels detected by `validate`, and
  rounds used (unless `--quiet`).
- Exit codes: `0` success; `2` input not found; `1` setup/API failure.
- Non-deterministic (generative). `--rounds` bounds cost (~1 generate + N−1
  revise calls; default 3 → ~3 vision calls).

## 5. Dependencies & error handling

- New extra: `[engine] = ["anthropic>=0.40", "resvg-py>=0.1.5", "pillow>=10.0"]`.
- **Requires an API key.** Unlike `--llm-refine`, there is no deterministic
  fallback — the LLM *is* the tool. A missing key or missing `[engine]` extra
  produces a clear setup/install message and exit 1.
- If a model reply has no parseable `<svg>`, retry within the remaining round
  budget; if still none, exit 1 with the raw reply truncated for debugging.
- If `render` fails on an interim SVG, skip that revise round (keep the current
  SVG) and warn.
- After the final round, run `validate`; if no wheels are detected, still write
  the file but print a warning that `extract_assets.js` may not find wheels.

## 6. Testing (TDD)

- **Pure/unit:** exemplar + conventions loading; `extract_svg` (fenced/prose
  wrapped → clean `<svg>`); `validate` (counts lower-region `#2c2c2a` wheel
  circles, checks viewBox presence); `render` returns non-empty PNG bytes for a
  known SVG.
- **Loop:** injected fake `generate`/`revise`/`render` (no network) → returns a
  valid SVG, respects `--rounds`, stops on "good"/unchanged.
- **Request assembly:** fake Anthropic client verifies the image blocks and model
  id are sent correctly (as in Stage 3's `make_suggester` test).
- **CLI:** missing input → exit 2; missing API key (monkeypatched generator
  raising) → exit 1 with a clear message; end-to-end with injected fakes writes
  a `.svg`.
- **Manual:** real generation on the user's locomotive photos with a live key.

## 7. Build order

1. Bundled exemplars + `[engine]` extra + packaging/console script.
2. Pure units: `extract_svg`, `validate`, `render`, `exemplars`.
3. Generation calls (`generate`, `revise`) with fake-client tests.
4. `generate_engine` loop with injected fakes.
5. CLI wiring + error handling.
6. README + manual generation run on a real photo.

## 8. Integration with TrainGame (informational)

Generated sprite faces right → treat as a `NO_MIRROR` asset. Drop the `.svg` into
`src/assets/engines/`, add it to the catalog/`gen_engines.js` list as desired, and
run `extract_assets.js` to refresh `manifest.json` (it derives `wheels[]`,
`baseline_y`, and natural size from the wheel circles). `enginegen` does none of
this automatically — it only produces the sprite.

## 9. Key facts (basis for this design)

- TrainGame's `extract_assets.js` auto-derives wheel metadata from `#2c2c2a`
  circles (radius ≥ threshold) in the bottom ~40% of the sprite, so conforming
  SVGs need no hand-authored metadata.
- The house style is small (~2–6 KB) hand-authored primitive-shape SVGs with a
  consistent palette and wheels-first layering — tractable for LLM authoring
  (unlike faithful complex tracing).
- Newest assets face right and are listed in `NO_MIRROR` in `gen_engines.js`.
- Model `claude-opus-4-8` per Anthropic guidance; vision + SVG authoring is where
  the strongest model matters most.
