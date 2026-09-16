"""The machine-wide list of cortex projects a bare ``cortex dashboard`` tracks.

``CORTEX_DASHBOARD_ROOTS`` names a tracked set, but only for a process that
inherits the operator's shell. A launcher clicked in Finder or the Dock does
not: it starts with a bare environment, so an exported variable never reaches
it and the dashboard it opens knows about no project at all. A list on disk is
the one thing both a shell and a clicked app can read.

The file is one absolute path per line; blank lines and ``#`` comments are
ignored, so an operator can hand-remove a project. ``cortex init`` appends the
repo it initialises, and a dashboard launched from inside a project appends
that project.

When the file does not exist yet it is seeded once from Claude Code's own
project list (``~/.claude.json``), so projects initialised before this module
existed appear without being re-initialised. That is a bounded source, not a
filesystem scan, and :func:`is_project` rejects its worktree entries by shape
(a worktree's ``.git`` is a file). The seed runs only while the file is absent:
after that the file is the source of truth, and a project the operator deleted
from it stays deleted.

Stdlib only — the dashboard stack lives in the base install (ADR-0039), but
``cortex init`` still imports this module without pulling in FastAPI/uvicorn
or any of the dashboard's own dependencies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def registry_path() -> Path:
    """Return ``${XDG_STATE_HOME:-~/.local/state}/cortex-command/projects``.

    Resolved per call so tests can redirect ``XDG_STATE_HOME`` or ``HOME``.
    """
    state_home = os.environ.get("XDG_STATE_HOME") or str(
        Path.home() / ".local" / "state"
    )
    return Path(state_home) / "cortex-command" / "projects"


def is_project(path: Path) -> bool:
    """Whether *path* is a cortex project a dashboard can render.

    ``.claude/`` is the dashboard lifespan's own root check, ``cortex/`` is the
    state it reads, and a ``.git`` *directory* excludes git worktrees, whose
    ``.git`` is a file — without that, every lifecycle worktree Claude Code has
    ever opened would appear as a duplicate of its repo.
    """
    return (
        (path / ".claude").is_dir()
        and (path / "cortex").is_dir()
        and (path / ".git").is_dir()
    )


def _read_lines(path: Path) -> list[Path]:
    entries: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(Path(line).expanduser())
    return entries


def _claude_code_projects() -> list[Path]:
    """Project paths Claude Code has opened, or an empty list on any failure."""
    try:
        data = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        return [Path(key) for key in data.get("projects", {})]
    except (OSError, ValueError, AttributeError):
        return []


def _write(path: Path, roots: list[Path]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join("%s\n" % root for root in roots)
        path.write_text(body, encoding="utf-8")
    except OSError:
        # A sandboxed session cannot write outside its grants. The list is a
        # convenience, so a failed write costs a project in the switcher,
        # never the launch.
        pass


def load_projects() -> list[Path]:
    """Return the registered projects that still exist, in file order."""
    path = registry_path()
    if path.exists():
        try:
            candidates = _read_lines(path)
        except OSError:
            return []
    else:
        candidates = sorted(
            (p for p in _claude_code_projects() if is_project(p)),
            key=lambda p: p.name.lower(),
        )
        _write(path, candidates)

    seen: set[Path] = set()
    projects: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen and is_project(resolved):
            seen.add(resolved)
            projects.append(resolved)
    return projects


def register_project(root: Path) -> None:
    """Add *root* to the list if it is a project and not already there."""
    root = root.resolve()
    if not is_project(root):
        return
    path = registry_path()
    # Seeds the file first when absent, so registering one project never
    # hides every other one the seed would have found.
    known = load_projects()
    if root in known:
        return
    try:
        existing = _read_lines(path) if path.exists() else []
    except OSError:
        return
    _write(path, existing + [root])
