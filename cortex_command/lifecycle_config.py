"""Minimal parser primitive for ``cortex/lifecycle.config.md`` frontmatter.

This module exposes three public symbols:

- :func:`read_branch_mode` — raw closed-set string (caller validates).
- :func:`read_commit_artifacts` — boolean for the ``commit-artifacts`` flag,
  defaulting to ``True`` to preserve the prose-resident default at
  ``skills/lifecycle/references/plan.md`` §5 and
  ``skills/lifecycle/references/complete-first-run.md`` Step 2.
- :func:`resolve_backlog_backend` — raw backend string from the nested
  ``backlog:`` block, defaulting to ``"cortex-backlog"`` for every degenerate
  input so a normal local repo stays byte-identical.

All other names are underscore-prefixed.
"""

from __future__ import annotations as _annotations

import pathlib as _pathlib
import sys as _sys

import yaml as _yaml


_CONFIG_RELPATH = "cortex/lifecycle.config.md"
_FRONTMATTER_DELIM = "---"
_FIELD_NAME = "branch-mode"
_COMMIT_ARTIFACTS_FIELD = "commit-artifacts"
_COMMIT_ARTIFACTS_DEFAULT = True
_BACKLOG_BLOCK_FIELD = "backlog"
_BACKLOG_BACKEND_FIELD = "backend"
_BACKLOG_BACKEND_DEFAULT = "cortex-backlog"

# Config-key inventory (backlog #372 dormant-config audit).
#
# Live-in-code: parsed by a Python consumer today. Live-in-prose: consumed by
# skill prose (the model reads the value), no Python parser by design.
# DORMANT: documented in the scaffolded asset and set in live configs, but
# honored by nothing — a consumer that silently starts parsing one of these
# would change workflow behavior in every repo that copied the asset, so any
# activation must be loud and deliberate (epic #371's activation guard).
_LIVE_CODE_KEYS = frozenset(
    {"branch-mode", "commit-artifacts", "backlog", "synthesizer_overnight_enabled"}
)
_LIVE_PROSE_KEYS = frozenset({"type", "test-command", "demo-command", "demo-commands"})
_DORMANT_KEYS = frozenset(
    {"skip-specify", "skip-review", "default-tier", "default-criticality"}
)
_KNOWN_KEYS = _LIVE_CODE_KEYS | _LIVE_PROSE_KEYS | _DORMANT_KEYS

# Once-per-process dedup so multi-read consumers (statusline, hooks) don't spam.
_WARNED_KEYS: set = set()


def _warn_config_keys(parsed: dict, config_path: _pathlib.Path) -> None:
    """Warn (stderr, once per process per key) on dormant or unknown
    frontmatter keys. Never raises and never changes any parsed value —
    fail-open by contract; this is the audit surface, not a validator."""
    for key in parsed:
        if not isinstance(key, str) or key in _WARNED_KEYS:
            continue
        if key in _DORMANT_KEYS:
            _WARNED_KEYS.add(key)
            print(
                f"warning: '{key}' in {config_path} is documented but not "
                "honored by any consumer — setting it currently has no effect",
                file=_sys.stderr,
            )
        elif key not in _KNOWN_KEYS:
            _WARNED_KEYS.add(key)
            print(
                f"warning: unknown lifecycle.config.md key '{key}' in "
                f"{config_path} — ignored",
                file=_sys.stderr,
            )


def _extract_frontmatter_text(text: str) -> str | None:
    """Return the YAML text between the two ``---`` delimiters, or ``None``.

    A leading ``---`` line opens the block; the next ``---`` line closes it.
    Returns ``None`` when no opening delimiter exists or no closing
    delimiter follows it.
    """
    lines = text.splitlines()
    opened = False
    start_idx = 0
    for idx, line in enumerate(lines):
        if line.strip() == _FRONTMATTER_DELIM:
            if not opened:
                opened = True
                start_idx = idx + 1
                continue
            return "\n".join(lines[start_idx:idx])
    return None


def read_branch_mode(repo_root: _pathlib.Path) -> str | None:
    """Read the raw ``branch-mode`` value from lifecycle.config.md frontmatter.

    Behavior contract (spec R2):

    - Missing file → ``None``.
    - Malformed YAML frontmatter → ``None`` plus a stderr warning naming
      the file and the parse error.
    - Field absent → ``None``.
    - Field present → the raw string value, whitespace-stripped.

    No closed-set validation is performed here; callers must enforce that.
    """
    config_path = _pathlib.Path(repo_root) / _CONFIG_RELPATH
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None

    frontmatter_text = _extract_frontmatter_text(text)
    if frontmatter_text is None:
        return None

    try:
        parsed = _yaml.safe_load(frontmatter_text)
    except _yaml.YAMLError as exc:
        print(
            f"warning: failed to parse YAML frontmatter in {config_path}: {exc}",
            file=_sys.stderr,
        )
        return None

    if not isinstance(parsed, dict):
        return None

    _warn_config_keys(parsed, config_path)
    value = parsed.get(_FIELD_NAME)
    if value is None:
        return None

    return str(value).strip()


def resolve_backlog_backend(repo_root: _pathlib.Path) -> str:
    """Resolve the active backlog backend from lifecycle.config.md frontmatter.

    Descends the nested ``backlog:`` mapping to read ``backend``. Designed to
    fail toward today's local behavior (spec R1): every degenerate input
    resolves to ``"cortex-backlog"``, and an explicit value is returned raw
    (whitespace-stripped). This function never returns ``None`` and never
    introspects installed plugins.

    Behavior contract:

    - Missing file → ``"cortex-backlog"``.
    - Malformed YAML frontmatter → ``"cortex-backlog"`` plus a stderr warning
      naming the file and the parse error.
    - Top-level not a mapping → ``"cortex-backlog"``.
    - ``backlog:`` block absent → ``"cortex-backlog"``.
    - Scalar ``backlog:`` value (not a mapping) → ``"cortex-backlog"`` (the
      explicit ``isinstance`` guard prevents an ``AttributeError``).
    - ``backend`` null/empty → ``"cortex-backlog"``.
    - ``backend`` present → the raw string value, whitespace-stripped.

    No closed-set validation is performed here; callers route on the value.
    """
    config_path = _pathlib.Path(repo_root) / _CONFIG_RELPATH
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return _BACKLOG_BACKEND_DEFAULT

    frontmatter_text = _extract_frontmatter_text(text)
    if frontmatter_text is None:
        return _BACKLOG_BACKEND_DEFAULT

    try:
        parsed = _yaml.safe_load(frontmatter_text)
    except _yaml.YAMLError as exc:
        print(
            f"warning: failed to parse YAML frontmatter in {config_path}: {exc}",
            file=_sys.stderr,
        )
        return _BACKLOG_BACKEND_DEFAULT

    if not isinstance(parsed, dict):
        return _BACKLOG_BACKEND_DEFAULT

    _warn_config_keys(parsed, config_path)
    backlog_block = parsed.get(_BACKLOG_BLOCK_FIELD)
    if not isinstance(backlog_block, dict):
        return _BACKLOG_BACKEND_DEFAULT

    value = backlog_block.get(_BACKLOG_BACKEND_FIELD)
    if value is None:
        return _BACKLOG_BACKEND_DEFAULT

    resolved = str(value).strip()
    if not resolved:
        return _BACKLOG_BACKEND_DEFAULT

    return resolved


def read_commit_artifacts(repo_root: _pathlib.Path) -> bool:
    """Read the ``commit-artifacts`` boolean from lifecycle.config.md frontmatter.

    Defaults to ``True`` (preserves the prose-resident default at
    ``skills/lifecycle/references/plan.md`` §5 and
    ``skills/lifecycle/references/complete-first-run.md`` Step 2):

    - Missing file → ``True``.
    - Malformed YAML frontmatter → ``True`` plus a stderr warning naming
      the file and the parse error.
    - Field absent → ``True``.
    - Field present, parses as boolean → returned boolean.
    - Field present, non-boolean → ``True`` plus a stderr warning naming
      the rejected raw value (default-safe — the consumers expect a bool).
    """
    config_path = _pathlib.Path(repo_root) / _CONFIG_RELPATH
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return _COMMIT_ARTIFACTS_DEFAULT

    frontmatter_text = _extract_frontmatter_text(text)
    if frontmatter_text is None:
        return _COMMIT_ARTIFACTS_DEFAULT

    try:
        parsed = _yaml.safe_load(frontmatter_text)
    except _yaml.YAMLError as exc:
        print(
            f"warning: failed to parse YAML frontmatter in {config_path}: {exc}",
            file=_sys.stderr,
        )
        return _COMMIT_ARTIFACTS_DEFAULT

    if not isinstance(parsed, dict):
        return _COMMIT_ARTIFACTS_DEFAULT

    _warn_config_keys(parsed, config_path)
    if _COMMIT_ARTIFACTS_FIELD not in parsed:
        return _COMMIT_ARTIFACTS_DEFAULT

    value = parsed[_COMMIT_ARTIFACTS_FIELD]
    if isinstance(value, bool):
        return value

    print(
        f"warning: {_COMMIT_ARTIFACTS_FIELD} in {config_path} is not a "
        f"boolean (got {value!r}); defaulting to {_COMMIT_ARTIFACTS_DEFAULT}",
        file=_sys.stderr,
    )
    return _COMMIT_ARTIFACTS_DEFAULT


def _main() -> int:
    """CLI entry point — prints ``true`` or ``false`` for the commit-artifacts flag.

    Invoked via ``python3 -m cortex_command.lifecycle_config`` or the
    ``cortex-read-commit-artifacts`` binstub. Resolves the user's cortex
    project root the same way every other project-aware consumer does, via
    ``cortex_command.common._resolve_user_project_root()`` (honor
    ``CORTEX_REPO_ROOT`` when set, else walk up from cwd to the nearest
    ``cortex/`` ancestor), falling open to the current working directory
    when no project is found. It does NOT read ``CORTEX_COMMAND_ROOT`` —
    that variable locates the cortex-command package, not the user's
    project. Output is lowercase with a trailing newline so shell consumers
    can match against ``true`` / ``false`` with a plain ``=`` comparison.
    """
    import os as _os

    from cortex_command.common import (
        CortexProjectRootError,
        _resolve_user_project_root,
    )

    try:
        root = _resolve_user_project_root()
    except CortexProjectRootError:
        root = _pathlib.Path(_os.getcwd())
    _sys.stdout.write("true\n" if read_commit_artifacts(root) else "false\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
