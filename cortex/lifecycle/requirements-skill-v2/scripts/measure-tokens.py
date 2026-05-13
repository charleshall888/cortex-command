#!/usr/bin/env python3
"""Measure cl100k_base token count of a file (default: cortex/requirements/project.md).

Iteration aid for the requirements-skill-v2 Phase 3 trim loop (Task 15).
Lives in the lifecycle directory as historical documentation of how the
trim target was measured; no production code depends on it.

Usage:
    uv run python cortex/lifecycle/requirements-skill-v2/scripts/measure-tokens.py
    uv run python cortex/lifecycle/requirements-skill-v2/scripts/measure-tokens.py path/to/other.md

Output format: "<path> <token-count>"
"""
from __future__ import annotations

import sys
from pathlib import Path

import tiktoken

DEFAULT_PATH = "cortex/requirements/project.md"


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else Path(DEFAULT_PATH)
    if not target.is_file():
        print(f"error: {target} not found (cwd={Path.cwd()})", file=sys.stderr)
        return 1
    text = target.read_text(encoding="utf-8")
    enc = tiktoken.get_encoding("cl100k_base")
    count = len(enc.encode(text))
    print(f"{target} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
