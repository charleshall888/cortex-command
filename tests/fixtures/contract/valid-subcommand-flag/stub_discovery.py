"""Stub module providing a minimal argparse parser for cortex-discovery.

Models the emit-research-sizing subcommand with --topic, --complexity,
and --criticality flags. Used by contract lint fixtures only — not a real
implementation.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cortex-discovery")
    sub = parser.add_subparsers(dest="command", required=True)

    ers = sub.add_parser("emit-research-sizing")
    ers.add_argument("--topic", required=True)
    ers.add_argument("--complexity", required=True)
    ers.add_argument("--criticality", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    parser.parse_args()
