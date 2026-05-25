"""cortex-critical-review-write-residue — atomic JSON writer for residue files.

Stub created by Task 4 of the convert-bin-cortex-and-skill-embedded feature.
Real logic is filled in by Task 6.

Usage:
    cortex-critical-review-write-residue --feature <slug>

Reads a JSON payload from stdin, validates ``--feature`` against
``^[a-z0-9][a-z0-9-]*$`` (rejecting otherwise with exit 2 and stderr
``invalid --feature: ...``), then performs a tempfile + ``os.replace``
atomic write to ``cortex/lifecycle/<feature>/critical-review-residue.json``.
Slug validation closes the path-traversal vector flagged in spec F4.
"""

from __future__ import annotations

import argparse
import re
from typing import List, Optional

from cortex_command.backlog import _telemetry


_FEATURE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _feature_slug(value: str) -> str:
    """argparse type-function: accept only matching slugs; reject otherwise."""
    if _FEATURE_SLUG_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(f"invalid --feature: {value}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-critical-review-write-residue",
        description=(
            "Read a JSON payload on stdin and atomically write it to "
            "cortex/lifecycle/<feature>/critical-review-residue.json. The "
            "--feature slug is validated against ^[a-z0-9][a-z0-9-]*$ to "
            "prevent path traversal."
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        type=_feature_slug,
        help="Lifecycle feature slug (matches ^[a-z0-9][a-z0-9-]*$).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-critical-review-write-residue")
    parser = _build_parser()
    parser.parse_args(argv)
    raise NotImplementedError("filled in by T6")


if __name__ == "__main__":
    main()
