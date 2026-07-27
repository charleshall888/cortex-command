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
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, NamedTuple, Optional

from cortex_command.backlog import _telemetry


_FEATURE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class _Resolved(NamedTuple):
    status: str
    feature: Optional[str]
    note: str


def _resolve_feature(session_id: str) -> _Resolved:
    """Map a lifecycle session id to its feature slug via ``.session`` files.

    Returns the note the caller relays verbatim on the two non-unique arms,
    so the skill carries no wording of its own for them.
    """
    matches = []
    for session_file in Path("cortex/lifecycle").glob("*/.session"):
        try:
            if session_file.read_text().strip() == session_id:
                matches.append(session_file)
        except OSError:
            continue
    if not matches:
        return _Resolved(
            "no-context",
            None,
            "Note: B-class residue not written — no active lifecycle context.",
        )
    if len(matches) > 1:
        return _Resolved(
            "ambiguous",
            None,
            f"Note: multiple active lifecycle sessions matched {session_id}; "
            f"B-class residue write skipped.",
        )
    return _Resolved("ok", matches[0].parent.name, "")


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
        type=_feature_slug,
        default=None,
        help="Lifecycle feature slug (matches ^[a-z0-9][a-z0-9-]*$).",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Resolve the feature from this session id instead of passing "
            "--feature (typically $LIFECYCLE_SESSION_ID). Zero or multiple "
            "matches skip the write and report why on stdout — the same "
            "no-lifecycle-context outcome, without a second round-trip."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-critical-review-write-residue")
    parser = _build_parser()
    args = parser.parse_args(argv)

    feature = args.feature
    if feature is None:
        if not args.session_id:
            print("one of --feature or --session-id is required", file=sys.stderr)
            return 2
        resolved = _resolve_feature(args.session_id)
        if resolved.status != "ok":
            print(json.dumps({"state": resolved.status, "note": resolved.note}))
            return 0
        feature = resolved.feature

    raw = sys.stdin.read()
    if not raw.strip():
        print("no payload on stdin", file=sys.stderr)
        return 2

    payload = json.loads(raw)
    data = json.dumps(payload, indent=2) + "\n"

    final = Path("cortex/lifecycle") / feature / "critical-review-residue.json"
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=str(final.parent), delete=False
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    os.replace(tmp_path, final)
    print(json.dumps({"state": "written", "feature": feature, "path": str(final)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
