"""cortex-debug-session-path — resolves the /cortex-core:diagnose skill's
Location-priority rule for where the debug session artifact lives (see
``skills/diagnose/references/debug-session-artifact.md``).

Before this verb, that rule was prose the model applied by hand: check for
an explicit feature argument, else read ``$LIFECYCLE_SESSION_ID`` and scan
``cortex/lifecycle/*/.session`` files for a match, else fall back to a
``cortex/debug/{date}-{slug}.md`` path. The prose carried a caveat that
``$LIFECYCLE_SESSION_ID`` propagation into overnight sub-agent sessions was
"unverified". This verb retires that caveat: it reads the env var and the
filesystem directly and always resolves to a well-defined path — whether or
not the env var happens to be set — rather than asking the model to reason
about whether its own environment carries the variable.

The session-match scan mirrors ``cortex_command.discovery._active_lifecycle_slug``'s
marker precedence (``.session``, then chain-migrated ``.session-owner``) and
its ``archive`` skip, applied directly under an already-resolved
``cortex/lifecycle/`` base rather than re-deriving it from a repo root.

Dumb arg-actor per ADR-0019 (see
``cortex/adr/0019-skill-helper-verb-backend-structural-guard.md``): this verb
resolves purely from the caller-passed ``--feature``/``--slug`` flags plus
env and filesystem state. It never writes the artifact itself — write
timing and content stay in skill prose; this verb only answers "where".

States:
  lifecycle — the artifact lives under a matched ``cortex/lifecycle/{feature}/``
              directory; ``basis`` is ``"explicit-feature"`` (an explicit
              ``--feature`` whose lifecycle directory exists) or
              ``"session-match"`` (``$LIFECYCLE_SESSION_ID`` matched a
              ``.session``/``.session-owner`` marker).
  fallback  — the artifact lives under ``cortex/debug/``; ``basis`` is
              ``"explicit-feature-missing"`` (an explicit ``--feature`` was
              given but has no lifecycle directory — carries a ``warning``
              to surface before writing) or ``"no-session"`` (no explicit
              feature and no active session match).
  error     — an unexpected exception (e.g. an unresolvable project root, or
              a ``--feature``/``--slug`` value that fails the path-safety
              check) escaped ``resolve_debug_session_path`` itself; ``main``
              catches it here so the CLI always emits a JSON struct and
              exits 0 rather than a traceback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root

KNOWN_STATES = ("lifecycle", "fallback", "error")

_SESSION_MARKERS = (".session", ".session-owner")


def _validated_slug(value: str, *, flag: str) -> str:
    """Return *value* stripped, after rejecting path-escape shapes.

    Both ``--feature`` and ``--slug`` become path components below, so a
    ``..`` or separator in either would let a caller write outside the
    intended ``cortex/lifecycle/`` or ``cortex/debug/`` directory.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{flag} must be non-empty")
    if "/" in stripped or "\\" in stripped or ".." in stripped:
        raise ValueError(
            f"{flag} must not contain path separators or '..': {stripped!r}"
        )
    return stripped


def _find_session_match(lifecycle_base: Path, session_id: str) -> Optional[str]:
    """Return the feature slug whose session marker byte-equals (stripped)
    *session_id*, or ``None`` if ``lifecycle_base`` is absent or no
    directory's marker matches."""
    if not lifecycle_base.is_dir():
        return None
    for candidate in sorted(lifecycle_base.iterdir()):
        if not candidate.is_dir() or candidate.name == "archive":
            continue
        for marker_name in _SESSION_MARKERS:
            marker = candidate / marker_name
            if not marker.is_file():
                continue
            try:
                content = marker.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content == session_id:
                return candidate.name
    return None


def _fallback_path(root: Path, slug: Optional[str]) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_slug = _validated_slug(slug, flag="--slug") if slug else "diagnose"
    return root / "cortex" / "debug" / f"{date}-{safe_slug}.md"


def resolve_debug_session_path(
    feature: Optional[str] = None,
    slug: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Resolve the diagnose skill's Location-priority rule to one path."""
    root = project_root or _resolve_user_project_root()
    lifecycle_base = root / "cortex" / "lifecycle"

    if feature:
        safe_feature = _validated_slug(feature, flag="--feature")
        feature_dir = lifecycle_base / safe_feature
        if feature_dir.is_dir():
            return {
                "state": "lifecycle",
                "path": str(feature_dir / "debug-session.md"),
                "basis": "explicit-feature",
            }
        return {
            "state": "fallback",
            "path": str(_fallback_path(root, slug)),
            "basis": "explicit-feature-missing",
            "warning": (
                f"cortex/lifecycle/{safe_feature}/ does not exist — "
                "falling back to the cortex/debug/ artifact."
            ),
        }

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "").strip()
    if session_id:
        match = _find_session_match(lifecycle_base, session_id)
        if match is not None:
            return {
                "state": "lifecycle",
                "path": str(lifecycle_base / match / "debug-session.md"),
                "basis": "session-match",
            }

    return {
        "state": "fallback",
        "path": str(_fallback_path(root, slug)),
        "basis": "no-session",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-debug-session-path",
        description=(
            "Resolve the diagnose skill's Location-priority rule (explicit "
            "--feature, active $LIFECYCLE_SESSION_ID match, or cortex/debug/ "
            "fallback) into a single {state, path, basis} struct on stdout "
            "(always exit 0)."
        ),
    )
    parser.add_argument(
        "--feature",
        default=None,
        help=(
            "Explicit lifecycle feature slug, e.g. from "
            "`/cortex-core:diagnose <feature>`. Omit to resolve the active "
            "$LIFECYCLE_SESSION_ID session instead."
        ),
    )
    parser.add_argument(
        "--slug",
        default=None,
        help=(
            "Kebab-case slug for the cortex/debug/ fallback filename. "
            "Defaults to 'diagnose' when omitted."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-debug-session-path")
    args = _build_parser().parse_args(argv)
    try:
        result = resolve_debug_session_path(feature=args.feature, slug=args.slug)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
