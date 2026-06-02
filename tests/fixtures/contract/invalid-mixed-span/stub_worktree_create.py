"""Stub module providing a minimal argparse parser for cortex-worktree-create.

Used by contract lint fixtures only — not a real implementation.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cortex-worktree-create")
    parser.add_argument("--feature", required=True)
    parser.add_argument("--base-branch")
    return parser


def main() -> None:
    parser = build_parser()
    parser.parse_args()
