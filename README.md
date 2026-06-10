# svgbuilder

Convert a raster image (jpg/webp/png) into a clean, simplified colored SVG.
One image per run. Deterministic, offline, scriptable.

## Requirements

**Python 3.10–3.13.** Python 3.14 is *not* supported: the `vtracer` 0.6.15
prebuilt wheel for CPython 3.14 segfaults whenever a tuning parameter is passed
(a pyo3/3.14 bug). Use a 3.10–3.13 interpreter until vtracer ships a fixed wheel.

## Install

    pipx install svgbuilder        # or: pip install .

Pulls in `vtracer` and `pillow`. If your system Python is 3.14 (or externally
managed), create a 3.12/3.13 virtualenv first:

    python3.12 -m venv .venv && . .venv/bin/activate
    pip install .

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

- `--colors N`            override palette size
- `--filter-speckle N`    higher = removes more small specks
- `--mode spline|polygon` smooth curves vs crisp edges
- `--max-size PX`         downscale longest edge (default 1000)
- `--no-smooth`           disable denoising before quantization
- `--bg auto|white|none`  background handling for transparent images
- `--auto`                tune params by render+score (needs the `[auto]` extra)
- `--auto-budget N`       max candidate evaluations for `--auto`/`--llm-refine` (default 6)
- `--llm-refine`          steer tuning with a Claude vision model (needs `[auto]`+`[llm]` + API key)
- `--llm-model NAME`      Claude model for `--llm-refine` (default `claude-opus-4-8`)
- `--quiet`               suppress non-error output

On success prints the output path plus stats (colors, path count, bytes).
Exit codes: `0` success, `2` input file not found, `1` processing/write failure.

### Auto-tuning (`--auto`)

With the `[auto]` extra installed (`pip install 'svgbuilder[auto]'`), `--auto`
renders each candidate SVG, scores it against the source with SSIM, and searches
the tracing parameters to keep the best-looking result:

    svgbuilder train.jpg --auto                 # default budget of 6 evaluations
    svgbuilder train.jpg --auto --auto-budget 10

It is fully deterministic and offline (no LLM). The success line then also
reports the best score and how many candidates were evaluated, e.g.
`[auto: score=0.804 in 8 evals]`.

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

## How it works

    load (RGBA) -> downscale -> denoise -> palette-quantize (Pillow FASTOCTREE)
    -> trace (VTracer spline) -> write .svg

Color quantization uses Pillow's deterministic FASTOCTREE with dithering off, so
the same input and flags always produce the same SVG.

## License

MIT
