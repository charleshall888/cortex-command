"""cortex-lifecycle-register-artifact — skip-if-present registration of a
produced lifecycle artifact into ``index.md``'s ``artifacts:`` inline array.

Each lifecycle phase produces one artifact (``research.md``, ``spec.md``,
``plan.md``, ``review.md``). The feature's ``index.md`` carries a running
``artifacts:`` inline flow list plus an ``updated:`` date, both hand-rendered
by ``create_index.py`` in a byte-shape (unquoted inline array, unquoted date,
bare ``null``) that the downstream stdlib readers parse and that PyYAML cannot
round-trip. The delegation/plan/review skill prose previously narrated the
"append the phase name to ``artifacts:`` and bump ``updated:``" edit as a
hand-executed recipe; this verb owns that mechanical edit as one call.

The edit is a regex capture-rewrite of the single ``artifacts:`` line (the
existing entries are preserved verbatim — their original quoting untouched —
and the new artifact appended bare, matching ``create_index._render_tags``'s
unquoted convention) followed by an ``updated:`` date bump, written via
``common.atomic_write``. It is idempotent: registering an artifact already
present in the array is a byte-level no-op (no write, ``updated:`` unchanged),
mirroring ``update_item._remove_uuid_from_blocked_by``'s change-detection skip.

States:
  registered      — the artifact was absent; it was appended and ``updated:``
                    bumped to today.
  already-present — the artifact was already in the array; the file is left
                    byte-for-byte untouched (no ``updated:`` bump).
  no-index        — ``{root}/cortex/lifecycle/{feature}/index.md`` does not
                    exist; nothing was written.
  error           — an unexpected exception (unresolvable project root, I/O
                    failure, a non-UTF-8 index.md decode failure) surfaced as a
                    state; ``message`` carries the diagnostic. ``register_artifact``
                    self-handles the common cases and ``main`` wraps the call in a
                    final never-crash net (matching the sibling verbs), so the CLI
                    always emits JSON and exits 0.

The write root resolves via ``_resolve_user_project_root_from_cwd`` (the
cwd-only resolver, matching this verb's Complete-phase-sibling call site) so
the file lands in the same tree the phase's other writes target. Root-resolution
invariant: ``enter`` resolves the project root via ``CORTEX_REPO_ROOT``
(env-honoring) while ``finalize`` and ``register-artifact`` resolve it from cwd;
callers must ensure the two agree (overnight runs with cwd == repo root).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
    atomic_write,
)

KNOWN_STATES = ("registered", "already-present", "no-index", "error")

ARTIFACT_CHOICES = ("research", "spec", "plan", "review")

# Single-line inline flow array: ``artifacts: [a, b]`` / ``artifacts: []``.
# Non-greedy inner group; ``.`` never crosses the newline, so the match is
# confined to the one frontmatter line.
_ARTIFACTS_RE = re.compile(r"^(artifacts:\s*\[)(.*?)(\])\s*$", re.MULTILINE)
_UPDATED_RE = re.compile(r"^(updated:\s*).*$", re.MULTILINE)


def _today() -> str:
    """Return today's UTC date as ``YYYY-MM-DD`` (date-only).

    Defined locally (not imported) so the test can monkeypatch it
    deterministically, matching ``create_index._today``.
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def register_artifact(
    feature: str,
    artifact: str,
    *,
    index_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Append *artifact* to *feature*'s ``index.md`` ``artifacts:`` array.

    Skip-if-present: an artifact already in the array is a byte-level no-op.
    Common failure modes (unresolvable root, I/O error) return an ``"error"``
    state; an unexpected error (e.g. a non-UTF-8 ``index.md`` that raises
    ``UnicodeDecodeError``) propagates to ``main``'s never-crash net (see the
    module docstring).
    """
    try:
        if index_path is not None:
            path = index_path
        else:
            root = project_root or _resolve_user_project_root_from_cwd()
            path = root / "cortex" / "lifecycle" / feature / "index.md"

        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"state": "no-index", "feature": feature, "artifact": artifact}

        rel = f"cortex/lifecycle/{feature}/index.md"
        match = _ARTIFACTS_RE.search(text)
        if match is None:
            # No artifacts: line to append to — treat as a malformed index.
            return {"state": "no-index", "feature": feature, "artifact": artifact}

        raw_entries = [e.strip() for e in match.group(2).split(",") if e.strip()]
        normalized = [e.strip("'\"") for e in raw_entries]
        if artifact in normalized:
            return {
                "state": "already-present",
                "feature": feature,
                "artifact": artifact,
                "path": rel,
            }

        new_inner = ", ".join(raw_entries + [artifact])
        new_text = _ARTIFACTS_RE.sub(
            lambda m: f"{m.group(1)}{new_inner}{m.group(3)}", text, count=1
        )
        today = _today()
        new_text = _UPDATED_RE.sub(lambda m: f"{m.group(1)}{today}", new_text, count=1)
        atomic_write(path, new_text)
        return {
            "state": "registered",
            "feature": feature,
            "artifact": artifact,
            "path": rel,
        }
    except CortexProjectRootError as exc:
        return {
            "state": "error",
            "message": f"could not resolve the project root: {exc}",
        }
    except OSError as exc:
        return {"state": "error", "message": f"index.md I/O failed: {exc}"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-register-artifact",
        description=(
            "Skip-if-present append of --artifact to the lifecycle index.md "
            "artifacts: array (with an updated: date bump), emitting a "
            "{state, ...} JSON struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug (e.g. my-feature).",
    )
    parser.add_argument(
        "--artifact",
        required=True,
        choices=ARTIFACT_CHOICES,
        help="The produced artifact to register (research|spec|plan|review).",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help=(
            "Project root under which cortex/lifecycle/{feature}/index.md is "
            "resolved; defaults to auto-resolution from cwd."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-register-artifact")
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root) if args.project_root else None
    try:
        result = register_artifact(
            args.feature, args.artifact, project_root=project_root
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
