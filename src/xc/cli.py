"""Command-line entry point for the xC starter package."""

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xc",
        description="Minimal xC starter command-line interface.",
    )
    parser.add_argument("text", nargs="*", help="text to echo")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(" ".join(args.text) if args.text else "xC starter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
