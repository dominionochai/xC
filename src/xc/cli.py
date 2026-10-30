"""Command-line entry point for the xC package."""

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xc",
        description="A minimal xC command-line interface.",
    )
    parser.add_argument("text", nargs="*", help="text to echo")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(" ".join(args.text) if args.text else "xC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
