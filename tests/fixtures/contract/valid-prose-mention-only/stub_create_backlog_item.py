"""Stub module providing a minimal argparse parser for cortex-create-backlog-item.

Used by contract lint fixtures only — not a real implementation.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cortex-create-backlog-item")
    parser.add_argument("--title", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--type", required=True)
    parser.add_argument("--body")
    return parser


def main() -> None:
    parser = build_parser()
    parser.parse_args()
