"""Template materialization core for ``cortex init``.

Walks ``cortex_command/init/templates/`` and materializes each file into the
target repo's root via :func:`cortex_command.common.atomic_write`. Also owns
the ``.cortex-init`` marker file (R4, R5, R20) and the ``.gitignore`` append
(R4). This module implements the additive baseline (``overwrite=False``,
``backup_dir=None``); Tasks 4, 5, 6 layer pre-flight gates, drift reporting,
and the ``--force`` backup path on top.

Exposed surface (consumed by Tasks 4, 5, 6, 9):
    scaffold(repo_root, *, overwrite, backup_dir) -> list[Path]
        Walk ``templates/`` and additively write each file that is absent on
        disk. Returns the list of files actually written (for stderr report).
    write_marker(repo_root, *, refresh) -> None
        Write or refresh ``.cortex-init`` JSON marker with ``cortex_version``
        and ``initialized_at``.
    ensure_gitignore(repo_root) -> None
        Idempotent ``.gitignore`` append of ``.cortex-init`` and
        ``.cortex-init-backup/``. Repairs orphan-prefix fragments left by a
        truncated prior append.
"""

from __future__ import annotations

import datetime
import importlib.metadata
import json
import re
from pathlib import Path

from cortex_command.common import atomic_write

_TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"

_MARKER_FILENAME = ".cortex-init"
_BACKUP_DIR_PATTERN = ".cortex-init-backup/"
_GITIGNORE_TARGETS = (_MARKER_FILENAME, _BACKUP_DIR_PATTERN)

# Any line starting with ``.cortex-init`` that is NOT exactly one of the two
# canonical targets is treated as an orphan-prefix fragment from a prior
# truncated append (e.g., ``.cortex-init-backu``). The scan-and-repair step
# removes each such line before the idempotent append.
_ORPHAN_RE = re.compile(r"^\.cortex-init(?:-backup)?.*$")


def _iter_template_files() -> list[Path]:
    """Return every regular file under ``_TEMPLATE_ROOT``, sorted for stability."""
    return sorted(p for p in _TEMPLATE_ROOT.rglob("*") if p.is_file())


def scaffold(
    repo_root: Path,
    *,
    overwrite: bool,
    backup_dir: Path | None,
) -> list[Path]:
    """Walk the shipped templates and additively write missing files.

    Args:
        repo_root: Target repo root. Each shipped template file is written
            to ``repo_root / <relative-path-from-templates>``.
        overwrite: If True, existing target files are overwritten (Task 6's
            ``--force`` path). If False (Task 3 baseline), existing files
            are left untouched.
        backup_dir: If not None (Task 6's ``--force`` path), callers supply
            a pre-created backup directory whose ``backup_existing`` helper
            has already captured the prior content. Task 3 baseline always
            receives ``None``.

    Returns:
        The list of paths that were written, as absolute paths under
        ``repo_root``. Task 9's handler uses this list for the stderr
        report.
    """
    written: list[Path] = []
    for template_path in _iter_template_files():
        rel = template_path.relative_to(_TEMPLATE_ROOT)
        dest = repo_root / rel
        if dest.exists() and not overwrite:
            continue
        content = template_path.read_text(encoding="utf-8")
        atomic_write(dest, content)
        written.append(dest)
    # ``backup_dir`` is part of the exposed signature for Task 6 consumers;
    # Task 3 baseline never uses it (overwrite=False path).
    del backup_dir
    return written


def write_marker(repo_root: Path, *, refresh: bool) -> None:
    """Write or refresh the ``.cortex-init`` marker file.

    The marker is a JSON object with ``cortex_version`` (from the installed
    package metadata) and ``initialized_at`` (ISO-8601 UTC timestamp). R20
    requires that ``--update`` refresh both fields unconditionally; the
    default invocation writes the marker only when absent.

    Args:
        repo_root: Target repo root; marker lands at ``repo_root / .cortex-init``.
        refresh: If True, overwrite an existing marker with current values
            (R20). If False, skip the write when the marker already exists.
    """
    marker_path = repo_root / _MARKER_FILENAME
    if marker_path.exists() and not refresh:
        return

    data = {
        "cortex_version": importlib.metadata.version("cortex-command"),
        "initialized_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    content = json.dumps(data, indent=2) + "\n"
    atomic_write(marker_path, content)


def ensure_gitignore(repo_root: Path) -> None:
    """Idempotently append marker patterns to ``.gitignore`` with orphan repair.

    Two-phase operation:
        (a) Orphan-prefix repair — scan existing lines for any match of
            ``^\\.cortex-init(?:-backup)?.*$`` that is NOT one of the
            canonical targets (``.cortex-init`` or ``.cortex-init-backup/``)
            and remove each orphan. Covers partial-failure recovery from a
            prior truncated append (e.g., ``.cortex-init-backu``).
        (b) Idempotent append — for each target pattern, append if absent
            via line-exact membership check. A leading ``\\n`` is inserted
            when the existing file does not end in a newline, so the
            appended pattern lands on its own line (R10's newline-safety
            acceptance).

    Creates ``.gitignore`` if absent.

    Args:
        repo_root: Target repo root.
    """
    gitignore_path = repo_root / ".gitignore"

    if gitignore_path.exists():
        original = gitignore_path.read_text(encoding="utf-8")
    else:
        original = ""

    # Phase (a): orphan-prefix repair. Split preserving line content; we
    # reconstruct with ``\n`` joins and a trailing newline so the output is
    # well-formed regardless of the input's trailing-newline state.
    lines = original.split("\n")
    # ``split`` on trailing newline produces a final empty element; track it
    # so we can round-trip files that do/don't end with a newline accurately.
    had_trailing_newline = original.endswith("\n") if original else False
    if had_trailing_newline:
        # Drop the synthetic empty tail introduced by ``split``.
        lines = lines[:-1]

    repaired: list[str] = []
    orphans_removed = False
    for line in lines:
        if _ORPHAN_RE.match(line) and line not in _GITIGNORE_TARGETS:
            orphans_removed = True
            continue
        repaired.append(line)

    # Reconstruct the current file content (after orphan repair, before append).
    if repaired:
        current = "\n".join(repaired) + ("\n" if had_trailing_newline else "")
    else:
        current = ""

    if orphans_removed:
        atomic_write(gitignore_path, current)
        original = current

    # Phase (b): idempotent append of each missing target pattern.
    existing_lines = set(repaired)
    to_append = [t for t in _GITIGNORE_TARGETS if t not in existing_lines]
    if not to_append:
        return

    new_content = original
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    new_content += "\n".join(to_append) + "\n"
    atomic_write(gitignore_path, new_content)
