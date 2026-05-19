"""Minimal parser primitive for ``cortex/lifecycle.config.md`` frontmatter.

This module exposes exactly one public symbol: :func:`read_branch_mode`.
All other names are underscore-prefixed to keep the public API surface
closed to one function (see spec R2 of
``lifecycle-implement-auto-enter-worktree-drop``). Callers are responsible
for validating the returned raw string against any closed set.
"""

from __future__ import annotations as _annotations

import pathlib as _pathlib
import sys as _sys

import yaml as _yaml


_CONFIG_RELPATH = "cortex/lifecycle.config.md"
_FRONTMATTER_DELIM = "---"
_FIELD_NAME = "branch-mode"


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

    value = parsed.get(_FIELD_NAME)
    if value is None:
        return None

    return str(value).strip()
