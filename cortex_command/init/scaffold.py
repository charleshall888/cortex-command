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
        Write or refresh ``.cortex-init`` JSON marker with ``cortex_version``,
        ``initialized_at``, and ``init_artifacts_hash``.
    ensure_gitignore(repo_root) -> None
        Idempotent ``.gitignore`` append of ``.cortex-init`` and
        ``.cortex-init-backup/``. Repairs orphan-prefix fragments left by a
        truncated prior append.
"""

from __future__ import annotations

import datetime
import hashlib
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
# Per #202, both marker and backup-dir live under the cortex/ umbrella.
# .claude/worktrees/ holds per-feature git worktrees created by the lifecycle
# (interactive sessions and pipeline dispatch) and must never be committed.
_GITIGNORE_TARGETS = (
    "cortex/.cortex-init",
    "cortex/.cortex-init-backup/",
    ".claude/worktrees/",
)

# Explicit ordered list of every template path whose bytes feed the init
# artifacts hash (Task 1). Paths are POSIX-relative from ``_TEMPLATE_ROOT``.
# Enumerated verbatim so the hash is deterministic across installs and does
# not silently expand if new templates are added. Update this tuple when a
# template is added or removed and bump the hash version accordingly.
_HASH_INPUT_TEMPLATES: tuple[str, ...] = (
    "cortex/lifecycle.config.md",
    "cortex/backlog/README.md",
    "cortex/lifecycle/README.md",
    "cortex/requirements/project.md",
)

# Target scaffold paths inspected by the content-aware decline gate (R19).
# A populated non-marker repo with any of these present fires the gate.
_CONTENT_DECLINE_TARGETS = ("cortex",)


def _compute_init_artifacts_hash() -> str:
    """Return a deterministic content hash over all init artifact inputs.

    Iterates ``_HASH_INPUT_TEMPLATES`` verbatim (no ``iterdir()``), reads each
    template's bytes via ``_TEMPLATE_ROOT.joinpath(...)``, normalizes each to
    a canonical form (CRLF→LF, BOM strip, single trailing newline), then
    feeds serialized literals that also affect init outputs:
    ``repr(_GITIGNORE_TARGETS)`` and the fixed string ``b"cortex/"``.

    The hash covers every user-visible init output so that ``cortex init
    --ensure`` can detect drift across CLI releases without a version bump.

    Returns:
        ``"v1:<sha256-hexdigest>"``
    """
    h = hashlib.sha256()
    for rel_posix in _HASH_INPUT_TEMPLATES:
        raw = _TEMPLATE_ROOT.joinpath(rel_posix).read_bytes()
        # Strip UTF-8 BOM if present.
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        # Normalize CRLF → LF.
        normalized = raw.replace(b"\r\n", b"\n")
        # Ensure exactly one trailing newline.
        normalized = normalized.rstrip(b"\n") + b"\n"
        h.update(normalized)
    # Append serialized literals that affect user-visible init outputs.
    h.update(repr(_GITIGNORE_TARGETS).encode())
    h.update(b"cortex/")
    return f"v1:{h.hexdigest()}"


class ScaffoldError(Exception):
    """Raised by pre-flight gates to signal ``cortex init`` should abort.

    The message text is surfaced verbatim on stderr by the handler (Task 9),
    which also translates the exception into exit code 2.
    """


def check_marker_decline(repo_root: Path) -> None:
    """R6 gate: refuse to re-initialize a repo that already has ``.cortex-init``.

    Raises:
        ScaffoldError: if ``repo_root / cortex / .cortex-init`` exists.
    """
    if (repo_root / "cortex" / _MARKER_FILENAME).exists():
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
    """R13 gate: refuse if ``cortex/`` resolves outside the repo.

    Returns the canonical cortex umbrella path (with trailing slash) that
    the handler threads into :func:`settings_merge.register` to close the
    TOCTOU window between pre-flight resolution and a re-resolve at
    registration time.

    If ``cortex/`` does not yet exist, no resolution is possible; the
    non-canonical path (still with trailing slash) is returned. Ancestor
    canonicalization is the handler's responsibility (it calls
    ``repo_root.resolve()`` before invoking any gate), which makes the
    non-canonical path consistent with what the future-created directory
    will resolve to.

    Args:
        repo_root: Target repo root. Must already be canonicalized by the
            caller (handler invariant).

    Returns:
        The canonical cortex-umbrella-path string with a trailing ``/``.

    Raises:
        ScaffoldError: if an existing ``cortex`` resolves to a
            location that is not a subpath of ``repo_root``.
    """
    cortex_path = repo_root / "cortex"

    # ``Path.exists`` follows symlinks by default and returns False for
    # dangling links. We want to catch dangling symlinks too, since a
    # dangling link pointing outside the repo is still a safety concern
    # (it will resolve on creation). ``lexists`` via ``follow_symlinks=False``
    # detects the link entry regardless of target validity.
    try:
        present = cortex_path.exists(follow_symlinks=False)
    except TypeError:
        # Python <3.12 fallback — shouldn't hit (project requires 3.12+),
        # but guard anyway via os.path.lexists.
        present = os.path.lexists(cortex_path)

    if not present:
        return str(cortex_path) + "/"

    cortex_canon = cortex_path.resolve(strict=False)
    root_canon = repo_root.resolve(strict=False)

    # APFS (macOS) preserves case but compares case-insensitively; ``resolve``
    # does not normalize case. Normalize both sides before the containment
    # check so the comparison matches filesystem semantics.
    cortex_norm = Path(os.path.normcase(str(cortex_canon)))
    root_norm = Path(os.path.normcase(str(root_canon)))

    # ``is_relative_to`` performs proper subpath containment; ``startswith``
    # would false-positive (e.g. ``/tmp/repository`` vs ``/tmp/repo``).
    if not cortex_norm.is_relative_to(root_norm):
        raise ScaffoldError(
            "`cortex init`: refusing to proceed — `cortex/` "
            "resolves outside the repo root."
        )

    return str(cortex_canon) + "/"

# Any line matching ``[cortex/].cortex-init[-backup]...`` that is NOT exactly
# one of the two canonical targets is treated as an orphan-prefix fragment
# from a prior truncated append (e.g., ``.cortex-init-backu`` or the post-#202
# variant ``cortex/.cortex-init-backu``). The scan-and-repair step removes
# each such line before the idempotent append.
_ORPHAN_RE = re.compile(r"^(?:cortex/)?\.cortex-init(?:-backup)?.*$")


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
        (``<repo_root>/cortex/.cortex-init-backup/<UTC-timestamp>``) so callers
        (Task 9's handler) can log it to stderr.
    """
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    backup_dir = repo_root / "cortex" / _BACKUP_DIR_ROOT / timestamp

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
    package metadata), ``initialized_at`` (ISO-8601 UTC timestamp), and
    ``init_artifacts_hash`` (``v1:<sha256>`` over all init artifact inputs).
    R20 requires that ``--update`` refresh all fields unconditionally; the
    default invocation writes the marker only when absent.

    Args:
        repo_root: Target repo root; marker lands at ``repo_root / cortex / .cortex-init``.
        refresh: If True, overwrite an existing marker with current values
            (R20). If False, skip the write when the marker already exists.
    """
    marker_path = repo_root / "cortex" / _MARKER_FILENAME
    if marker_path.exists() and not refresh:
        return

    data = {
        "cortex_version": importlib.metadata.version("cortex-command"),
        "initialized_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "init_artifacts_hash": _compute_init_artifacts_hash(),
    }
    content = json.dumps(data, indent=2) + "\n"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(marker_path, content)


_PEP440_APPROX_RE = re.compile(r"^\d+\.\d+")
"""Lightweight PEP 440 version heuristic — checks that the string starts with
``<major>.<minor>`` (e.g. ``"1.2.3"``, ``"0.1.0.dev4"``). Not a full PEP 440
validator; sufficient to discriminate a cortex provenance signal from an
obviously-foreign value.  See spec R8 and plan Risks §PEP 440."""


def _read_marker_provenance(
    repo_root: Path,
) -> tuple[str | None, str | None]:
    """Read ``.cortex-init`` and return ``(init_artifacts_hash, cortex_version)``.

    R8 discrimination logic:
        - Marker absent → ``(None, None)`` (marker-absent signal; caller uses
          this to distinguish the first-init path from a recovery path).
        - Marker present but JSON unparseable (``JSONDecodeError``) → raises
          :class:`ScaffoldError` naming "unparseable JSON" so truncated writes
          and hand-edit syntax errors surface cleanly rather than silently
          mis-routing to the recovery path.
        - Marker present + valid JSON + ``init_artifacts_hash`` field present →
          ``(hash_value, cortex_version_or_None)`` (fully-populated marker).
        - Marker present + valid JSON + ``init_artifacts_hash`` absent +
          ``cortex_version`` present-and-parseable-PEP-440 → ``(None, version)``
          (signals R8 recovery-via-refresh; the caller emits the refresh warning
          and routes through the ``--update`` code path).
        - Marker present + valid JSON + ``init_artifacts_hash`` absent +
          ``cortex_version`` absent-or-malformed → raises :class:`ScaffoldError`
          with the R8 foreign-artifact diagnostic (no silent dispatch).

    Args:
        repo_root: Target repo root.

    Returns:
        A ``(init_artifacts_hash, cortex_version)`` pair where either element
        may be ``None``.  Both ``None`` means the marker is absent.

    Raises:
        ScaffoldError: On JSON parse failure or foreign-artifact discrimination.
    """
    marker_path = repo_root / "cortex" / _MARKER_FILENAME
    if not marker_path.exists():
        return (None, None)

    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScaffoldError(
            f"`cortex init --ensure`: {marker_path} contains unparseable JSON "
            f"({exc}); cannot determine cortex provenance. Remove the file and "
            "run `cortex init` to reinitialize, or `cortex init --force` to "
            "overwrite."
        ) from exc

    init_hash = data.get("init_artifacts_hash")  # may be None
    cortex_version = data.get("cortex_version")

    if init_hash is not None:
        # Fully-populated marker: return both fields.
        return (str(init_hash), str(cortex_version) if cortex_version is not None else None)

    # init_artifacts_hash missing — R8 provenance discrimination.
    if cortex_version is not None and _PEP440_APPROX_RE.match(str(cortex_version)):
        # Looks like a legitimate pre-Phase-1 cortex marker; route to recovery.
        return (None, str(cortex_version))

    # cortex_version absent or malformed — treat as foreign artifact.
    raise ScaffoldError(
        "`cortex init --ensure`: cortex/.cortex-init exists but lacks "
        "`cortex_version` field (or the value is not a recognizable version "
        "string); this does not look like a cortex marker. Run `cortex init` "
        "manually to confirm scaffolding intent."
    )


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
    # Uncomment to gitignore cortex tool state
    if "# cortex/" not in existing_lines:
        new_content += "# cortex/\n"
    atomic_write(gitignore_path, new_content)
