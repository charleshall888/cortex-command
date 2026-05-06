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
        disk. When ``overwrite`` is True, existing destinations are backed
        up via :func:`backup_existing` before being rewritten.
    backup_existing(repo_root, *, targets) -> Path
        Copy each existing ``targets`` file into
        ``.cortex-init-backup/<UTC-timestamp>/<relative-path>`` and return
        the backup directory path for stderr logging (R10).
    drift_files(repo_root) -> list[Path]
        Return scaffold target paths (relative to ``repo_root``) whose
        on-disk bytes differ from the shipped template bytes after ``\\r\\n``
        → ``\\n`` line-ending normalization. Consumed by ``--update`` for
        R9's drift report.
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
import os
import re
from collections.abc import Iterable
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from cortex_command.common import atomic_write

_TEMPLATE_ROOT: Traversable = files("cortex_command.init.templates")

_MARKER_FILENAME = ".cortex-init"
_BACKUP_DIR_PATTERN = ".cortex-init-backup/"
_BACKUP_DIR_ROOT = ".cortex-init-backup"
_GITIGNORE_TARGETS = (_MARKER_FILENAME, _BACKUP_DIR_PATTERN)

# Target scaffold paths inspected by the content-aware decline gate (R19).
# A populated non-marker repo with any of these present fires the gate.
_CONTENT_DECLINE_TARGETS = (
    "lifecycle",
    "backlog",
    "requirements",
    "lifecycle.config.md",
)


class ScaffoldError(Exception):
    """Raised by pre-flight gates to signal ``cortex init`` should abort.

    The message text is surfaced verbatim on stderr by the handler (Task 9),
    which also translates the exception into exit code 2.
    """


def check_marker_decline(repo_root: Path) -> None:
    """R6 gate: refuse to re-initialize a repo that already has ``.cortex-init``.

    Raises:
        ScaffoldError: if ``repo_root / .cortex-init`` exists.
    """
    if (repo_root / _MARKER_FILENAME).exists():
        raise ScaffoldError(
            "`cortex init`: repo already initialized. Use `--update` to add "
            "missing templates or `--force` to overwrite."
        )


def _target_has_content(path: Path) -> bool:
    """Return True if ``path`` exists and is non-empty (dir) or present (file)."""
    if not path.exists():
        return False
    if path.is_dir():
        # Any child entry counts as non-empty.
        return any(path.iterdir())
    # Regular file (or symlink to one) — presence alone is "content".
    return True


def check_content_decline(repo_root: Path) -> None:
    """R19 gate: refuse if any target scaffold path exists with content.

    Precondition: caller has already confirmed the ``.cortex-init`` marker is
    absent (R6 runs first). This gate inspects the five target paths and
    fires if any one is a non-empty directory or a present file.

    Raises:
        ScaffoldError: if any target scaffold path exists non-empty.
    """
    for rel in _CONTENT_DECLINE_TARGETS:
        if _target_has_content(repo_root / rel):
            raise ScaffoldError(
                "`cortex init`: one or more target paths exist with "
                "pre-existing content (no `.cortex-init` marker). Run "
                "`cortex init --update` to add missing templates without "
                "overwriting, or `cortex init --force` to overwrite with "
                "backup."
            )


def check_symlink_safety(repo_root: Path) -> str:
    """R13 gate: refuse if ``lifecycle/`` resolves outside the repo.

    Returns the canonical lifecycle path (with trailing slash) that the
    handler threads into :func:`settings_merge.register` to close the TOCTOU
    window between pre-flight resolution and a re-resolve at registration
    time.

    If ``lifecycle/`` does not yet exist, no resolution is possible;
    the non-canonical path (still with trailing slash) is returned. Ancestor
    canonicalization is the handler's responsibility (it calls
    ``repo_root.resolve()`` before invoking any gate), which makes the
    non-canonical path consistent with what the future-created directory
    will resolve to.

    Args:
        repo_root: Target repo root. Must already be canonicalized by the
            caller (handler invariant).

    Returns:
        The canonical lifecycle-path string with a trailing ``/``.

    Raises:
        ScaffoldError: if an existing ``lifecycle`` resolves to a
            location that is not a subpath of ``repo_root``.
    """
    lifecycle_path = repo_root / "lifecycle"

    # ``Path.exists`` follows symlinks by default and returns False for
    # dangling links. We want to catch dangling symlinks too, since a
    # dangling link pointing outside the repo is still a safety concern
    # (it will resolve on creation). ``lexists`` via ``follow_symlinks=False``
    # detects the link entry regardless of target validity.
    try:
        present = lifecycle_path.exists(follow_symlinks=False)
    except TypeError:
        # Python <3.12 fallback — shouldn't hit (project requires 3.12+),
        # but guard anyway via os.path.lexists.
        present = os.path.lexists(lifecycle_path)

    if not present:
        return str(lifecycle_path) + "/"

    lifecycle_canon = lifecycle_path.resolve(strict=False)
    root_canon = repo_root.resolve(strict=False)

    # APFS (macOS) preserves case but compares case-insensitively; ``resolve``
    # does not normalize case. Normalize both sides before the containment
    # check so the comparison matches filesystem semantics.
    lifecycle_norm = Path(os.path.normcase(str(lifecycle_canon)))
    root_norm = Path(os.path.normcase(str(root_canon)))

    # ``is_relative_to`` performs proper subpath containment; ``startswith``
    # would false-positive (e.g. ``/tmp/repository`` vs ``/tmp/repo``).
    if not lifecycle_norm.is_relative_to(root_norm):
        raise ScaffoldError(
            "`cortex init`: refusing to proceed — `lifecycle/` "
            "resolves outside the repo root."
        )

    return str(lifecycle_canon) + "/"

# Any line starting with ``.cortex-init`` that is NOT exactly one of the two
# canonical targets is treated as an orphan-prefix fragment from a prior
# truncated append (e.g., ``.cortex-init-backu``). The scan-and-repair step
# removes each such line before the idempotent append.
_ORPHAN_RE = re.compile(r"^\.cortex-init(?:-backup)?.*$")


def _iter_template_files() -> list[tuple[Traversable, Path]]:
    """Return every regular file under ``_TEMPLATE_ROOT``, sorted for stability.

    Each entry is ``(traversable, relative_path)`` where ``traversable`` is
    the resource handle (suitable for ``.read_text()`` / ``.read_bytes()``)
    and ``relative_path`` is the path relative to ``_TEMPLATE_ROOT`` used to
    derive on-disk destinations under ``repo_root``.

    Walks the package resource tree via ``iterdir()`` recursively so the
    traversal works under both editable and non-editable wheel installs
    (``importlib.resources.Traversable`` does not expose ``rglob``).
    """
    results: list[tuple[Traversable, Path]] = []

    def _walk(node: Traversable, rel: Path) -> None:
        for child in node.iterdir():
            child_rel = rel / child.name
            if child.is_file():
                results.append((child, child_rel))
            elif child.is_dir():
                _walk(child, child_rel)

    _walk(_TEMPLATE_ROOT, Path())
    results.sort(key=lambda entry: entry[1])
    return results


def scaffold(
    repo_root: Path,
    *,
    overwrite: bool,
    backup_dir: Path | None,
) -> list[Path]:
    """Walk the shipped templates and write files, optionally with backup.

    Args:
        repo_root: Target repo root. Each shipped template file is written
            to ``repo_root / <relative-path-from-templates>``.
        overwrite: If True, existing target files are overwritten (Task 6's
            ``--force`` path). Any existing destination is first copied
            into a timestamped backup directory under
            ``.cortex-init-backup/`` via :func:`backup_existing` (unless
            the caller pre-supplied ``backup_dir``). If False (Task 3
            baseline), existing files are left untouched.
        backup_dir: If not None, the caller has already captured prior
            content via :func:`backup_existing` (Task 9's handler does
            this so it can log the backup directory before invoking
            scaffold). Scaffold will overwrite existing files without
            re-backing them up. If None and ``overwrite`` is True,
            scaffold calls :func:`backup_existing` itself for any
            destinations that already exist.

    Returns:
        The list of paths that were written, as absolute paths under
        ``repo_root``. Task 9's handler uses this list for the stderr
        report.
    """
    written: list[Path] = []

    if overwrite and backup_dir is None:
        # Collect existing destinations up front so the backup lands under
        # one timestamp directory rather than spawning a fresh dir per
        # file (which the per-second ``%Y-%m-%dT%H-%M-%SZ`` format would
        # collapse anyway, but this is cleaner and avoids the edge case
        # where two iterations of the loop straddle a second boundary).
        existing_targets: list[Path] = []
        for _template, rel in _iter_template_files():
            dest = repo_root / rel
            if dest.exists():
                existing_targets.append(dest)
        if existing_targets:
            backup_existing(repo_root, targets=existing_targets)

    for template, rel in _iter_template_files():
        dest = repo_root / rel
        if dest.exists() and not overwrite:
            continue
        content = template.read_text(encoding="utf-8")
        atomic_write(dest, content)
        written.append(dest)
    return written


def backup_existing(
    repo_root: Path,
    *,
    targets: Iterable[Path],
) -> Path:
    """Copy each existing ``targets`` file into a timestamped backup dir.

    Backups land at ``<repo_root>/.cortex-init-backup/<UTC-timestamp>/<rel>``
    where ``<rel>`` is each target path's position relative to
    ``repo_root``. The timestamp uses ``%Y-%m-%dT%H-%M-%SZ`` (colons
    replaced with hyphens so the path is portable across filesystems
    that treat ``:`` specially — e.g., Windows). Files are copied via
    :func:`cortex_command.common.atomic_write`; non-existent targets and
    directories are skipped (R10 backs up the file contents of each of
    the five scaffold targets, not empty-dir shells).

    Args:
        repo_root: Target repo root. The backup tree is created under
            ``repo_root / .cortex-init-backup / <timestamp> /``.
        targets: Iterable of paths (absolute or under ``repo_root``) to
            back up. Each path is made relative to ``repo_root`` to
            compute its backup destination.

    Returns:
        The absolute backup directory path
        (``<repo_root>/.cortex-init-backup/<UTC-timestamp>``) so callers
        (Task 9's handler) can log it to stderr.
    """
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    backup_dir = repo_root / _BACKUP_DIR_ROOT / timestamp

    for target in targets:
        src = Path(target)
        if not src.is_absolute():
            src = repo_root / src
        if not src.exists() or not src.is_file():
            # R10 backs up file content; directories are recreated by
            # the shipped templates on overwrite.
            continue
        rel = src.relative_to(repo_root)
        dest = backup_dir / rel
        content = src.read_text(encoding="utf-8")
        atomic_write(dest, content)

    return backup_dir


def drift_files(repo_root: Path) -> list[Path]:
    """Return scaffold target paths whose on-disk bytes differ from shipped.

    For each shipped template file under ``_TEMPLATE_ROOT``, compares the
    shipped bytes against ``repo_root / <relative-path>`` after normalizing
    ``\\r\\n`` → ``\\n`` on both sides. Missing on-disk files are skipped
    (they are handled by :func:`scaffold`, not drift). Byte-for-byte matches
    after normalization are not drift.

    Used by ``--update`` (R9) to emit the stderr drift report; the handler
    formats the returned relative paths as a bulleted list plus a
    ``--force`` hint line.

    Args:
        repo_root: Target repo root. Relative paths in the return list are
            anchored here.

    Returns:
        Sorted list of paths (relative to ``repo_root``) whose on-disk
        content differs from the shipped template after line-ending
        normalization. Empty list means no drift.
    """
    drifted: list[Path] = []
    for template, rel in _iter_template_files():
        dest = repo_root / rel
        if not dest.exists():
            # Missing files are a scaffold concern, not a drift concern.
            continue
        shipped = template.read_bytes().replace(b"\r\n", b"\n")
        on_disk = dest.read_bytes().replace(b"\r\n", b"\n")
        if shipped != on_disk:
            drifted.append(rel)
    return drifted


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
