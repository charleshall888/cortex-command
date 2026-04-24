"""Flock-protected additive merge for ``~/.claude/settings.local.json``.

Owns the only ``~/.claude/`` write surface in cortex-command: an additive
append to the ``sandbox.filesystem.allowWrite`` array. Concurrent callers
serialize through a sibling lockfile at ``~/.claude/.settings.local.json.lock``
(see spec R11, R12, R14, ADR-2).

Sibling-lockfile rationale (supersedes spec ADR-2's "lock the file itself"
phrasing): ``atomic_write`` performs ``os.replace(tmp, settings_path)`` which
swaps the inode at ``settings.local.json``. ``fcntl.flock`` is an advisory
lock on a specific inode — after a first caller's ``os.replace``, a second
caller that opens ``settings.local.json`` gets an fd on the NEW inode and
acquires an independent (non-contending) ``LOCK_EX``, defeating the intent
of ADR-2. The stable sibling lockfile inode is never replaced, so
``fcntl.flock`` there actually serializes all callers.

Exposed surface:
    SettingsMergeError        -- raised for malformed sandbox types and
                                 invalid-JSON content.
    register(repo_root,        -- additive append of ``target_path`` to
            target_path,         ``sandbox.filesystem.allowWrite``.
            *, home=None)
    validate_settings(         -- pre-flight-only R14 gate. No mutation.
            home=None)
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from cortex_command.common import atomic_write


class SettingsMergeError(Exception):
    """Raised when the settings.local.json merge cannot proceed safely.

    Task 9's handler catches this and translates to exit code 2. Covers:
        * malformed ``.sandbox`` or ``.sandbox.filesystem`` types (R14)
        * invalid JSON in ``settings.local.json`` (edge case)
        * unrecoverable I/O conditions during the read-mutate-write cycle
    """


def _claude_dir(home: Path | None) -> Path:
    """Return ``<home>/.claude`` (default ``Path.home()``)."""
    return (home or Path.home()) / ".claude"


def _settings_path(home: Path | None) -> Path:
    """Return the ``~/.claude/settings.local.json`` path."""
    return _claude_dir(home) / "settings.local.json"


def _lockfile_path(home: Path | None) -> Path:
    """Return the sibling lockfile path.

    Sibling (not the settings file itself) so the lock survives
    ``atomic_write``'s ``os.replace`` swapping the settings-file inode.
    """
    return _claude_dir(home) / ".settings.local.json.lock"


def _acquire_lock(home: Path | None) -> int:
    """Create/open the sibling lockfile and acquire ``LOCK_EX``.

    Returns the raw file descriptor. Caller must release via ``os.close(fd)``
    in a ``try/finally``. The lockfile is created with mode ``0o600`` and
    contains no payload.
    """
    claude_dir = _claude_dir(home)
    claude_dir.mkdir(parents=True, exist_ok=True)
    lockfile_path = _lockfile_path(home)
    lock_fd = os.open(lockfile_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except BaseException:
        os.close(lock_fd)
        raise
    return lock_fd


def _read_settings(settings_path: Path) -> dict:
    """Read and parse settings.local.json.

    Returns an empty dict if the file is absent (fresh install).
    Raises ``SettingsMergeError`` on invalid JSON.
    """
    if not settings_path.exists():
        return {}

    raw = settings_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise SettingsMergeError(
            f"settings.local.json: invalid JSON at line {exc.lineno}:{exc.colno}"
        ) from exc

    if not isinstance(data, dict):
        raise SettingsMergeError(
            f"~/.claude/settings.local.json: expected top-level object, got "
            f"{type(data).__name__}"
        )
    return data


def _validate_sandbox_shape(data: dict) -> None:
    """Pre-validate that ``.sandbox`` and ``.sandbox.filesystem`` are objects.

    R14: if either exists but is not a dict, raise with a clear diagnostic.
    Absent keys are fine — the merge will create them.
    """
    if "sandbox" in data and not isinstance(data["sandbox"], dict):
        raise SettingsMergeError(
            f"~/.claude/settings.local.json: expected sandbox to be an "
            f"object, got {type(data['sandbox']).__name__}"
        )
    sandbox = data.get("sandbox")
    if isinstance(sandbox, dict) and "filesystem" in sandbox:
        if not isinstance(sandbox["filesystem"], dict):
            raise SettingsMergeError(
                f"~/.claude/settings.local.json: expected sandbox.filesystem "
                f"to be an object, got {type(sandbox['filesystem']).__name__}"
            )


def register(
    repo_root: Path,
    target_path: str,
    *,
    home: Path | None = None,
) -> None:
    """Additively register ``target_path`` in ``sandbox.filesystem.allowWrite``.

    Serializes the full read-validate-mutate-write cycle under an advisory
    lock on a stable sibling lockfile inode.

    Args:
        repo_root: The repo root (retained for diagnostic messages; the
            caller has already resolved/canonicalized ``target_path``).
        target_path: The already-resolved, canonicalized ``lifecycle/sessions/``
            path (trailing slash) to append to ``allowWrite``. Caller is
            Task 9's handler, which obtains this from the R13 symlink-safety
            gate (Task 3).
        home: Optional HOME override (tests).

    Behavior:
        * Creates ``~/.claude/`` if absent.
        * Creates ``settings.local.json`` with a minimal
          ``{"sandbox": {"filesystem": {"allowWrite": [target_path]}}}``
          if the file is absent.
        * Pre-validates ``.sandbox`` and ``.sandbox.filesystem`` are objects
          (R14); raises ``SettingsMergeError`` with a clear diagnostic
          otherwise.
        * Order-preserving idempotent append: if ``target_path`` is already
          present, the array is unchanged (no duplicate, no reorder).
        * Preserves all other existing keys (``permissions.allow``,
          ``sandbox.network.*``, etc.) byte-for-byte in the non-mutated
          subtrees.
        * Writes via ``cortex_command.common.atomic_write`` (tempfile +
          ``os.replace``, with ``durable_fsync``).

    Raises:
        SettingsMergeError: malformed sandbox types, invalid JSON, or an
            underlying OSError surfaced for the handler to translate to
            exit code 2.
    """
    # repo_root is carried purely for diagnostic messages; resolution happened
    # upstream (see Task 3 — check_symlink_safety returns the canonical path).
    del repo_root

    settings_path = _settings_path(home)
    lock_fd = _acquire_lock(home)
    try:
        data = _read_settings(settings_path)
        _validate_sandbox_shape(data)

        sandbox = data.setdefault("sandbox", {})
        filesystem = sandbox.setdefault("filesystem", {})
        allow_array = filesystem.setdefault("allowWrite", [])
        if not isinstance(allow_array, list):
            raise SettingsMergeError(
                f"~/.claude/settings.local.json: expected "
                f"sandbox.filesystem.allowWrite to be an array, got "
                f"{type(allow_array).__name__}"
            )

        # Order-preserving idempotent append. Do NOT use set() — would
        # reorder the user's existing allowWrite entries.
        if target_path not in allow_array:
            allow_array.append(target_path)

        content = json.dumps(data, indent=2) + "\n"
        atomic_write(settings_path, content)
    finally:
        os.close(lock_fd)


def validate_settings(home: Path | None = None) -> None:
    """Pre-flight-only R14 gate. Validate sandbox shape without mutating.

    Acquires the sibling lockfile, reads ``settings.local.json`` (if
    present), validates ``.sandbox`` and ``.sandbox.filesystem`` are objects
    (or absent), releases the lock. No write side effect.

    Called from Task 9's handler (step 3) before any repo mutation so that
    ADR-3's ordering invariant holds: R14 fires in pre-flight, with zero
    filesystem mutation on failure.

    Args:
        home: Optional HOME override (tests).

    Raises:
        SettingsMergeError: malformed sandbox types or invalid JSON in the
            existing ``settings.local.json``.
    """
    settings_path = _settings_path(home)
    lock_fd = _acquire_lock(home)
    try:
        data = _read_settings(settings_path)
        _validate_sandbox_shape(data)
    finally:
        os.close(lock_fd)
