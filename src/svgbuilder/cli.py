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
    p.add_argument("--auto", action="store_true",
                   help="Auto-tune tracing parameters by rendering and scoring "
                        "candidates (needs the [auto] extra).")
    p.add_argument("--auto-budget", type=int, default=6, dest="auto_budget",
                   help="Max candidate evaluations for --auto/--llm-refine (default 6).")
    p.add_argument("--llm-refine", action="store_true", dest="llm_refine",
                   help="Use a Claude vision model to steer auto-tuning (needs the "
                        "[auto] and [llm] extras + an API key). Falls back to --auto "
                        "if unavailable.")
    p.add_argument("--llm-model", default="claude-opus-4-8", dest="llm_model",
                   help="Claude model for --llm-refine (default claude-opus-4-8).")
    p.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    p.add_argument("--version", action="version", version=f"svgbuilder {__version__}")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    auto_info = None
    try:
        params = build_params(args.preset, args.colors, args.filter_speckle, args.mode)
        img = load_image(args.input, max_size=args.max_size, bg=args.bg)
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
        line = (f"wrote {out_path}  "
                f"(colors={params['colors']}, paths={svg.count('<path')}, "
                f"bytes={len(svg)})")
        if auto_info:
            line += f"  [{auto_info}]"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
