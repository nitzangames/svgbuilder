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
