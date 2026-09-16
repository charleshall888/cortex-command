"""The hash-locked, allowlisted, atomic write behind the Docs view's edit form.

The only place the dashboard writes a repo file. Rails, in order:

* the path must be a governing, existing node of the corpus built from the
  request's root — never a path constructed from user input;
* the file must resolve inside the root and must not be a symlink;
* the caller's ``expected_sha`` must equal the hash of what is on disk *now*
  (content hash, not mtime — same-length edits are invisible to mtime-only
  checks), else the save is refused as a conflict and the disk text is
  returned for the operator to reconcile;
* the write is a same-directory temp file + ``os.replace``, mode preserved.

No git: the change shows up in ``git status`` and whichever session commits
next carries it. Nothing here raises on the happy or conflict paths.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cortex_command.dashboard.docs.model import Corpus


@dataclass(frozen=True)
class EditView:
    path: str
    text: str
    sha: str


@dataclass(frozen=True)
class SaveResult:
    ok: bool
    reason: str | None          # None on a clean save; ``unchanged`` / ``conflict`` / a refusal word
    sha: str                    # hash of what is on disk after the call
    disk_text: str | None = None   # the disk version, returned on ``conflict`` only


def content_hash(text: str) -> str:
    """sha256 hex of *text*'s UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _target(root: Path, corpus: Corpus, path: str) -> tuple[Path | None, str | None]:
    """Resolve *path* through the rails. Returns ``(file, None)`` or ``(None, reason)``."""
    node = corpus.get(path)
    if node is None or not node.governing or not node.exists:
        return None, "not-governing"
    lexical = root / path
    try:
        if lexical.is_symlink():
            return None, "symlink"
        resolved = lexical.resolve()
        if not resolved.is_relative_to(root.resolve()):
            return None, "outside-root"
        if not resolved.is_file():
            return None, "missing"
    except OSError:
        return None, "unreadable"
    return resolved, None


def read_for_edit(root: Path, corpus: Corpus, path: str) -> EditView | None:
    """The current text and its hash, or None when *path* is not editable."""
    target, _ = _target(root, corpus, path)
    if target is None:
        return None
    try:
        text = _decode(target.read_bytes())
    except OSError:
        return None
    return EditView(path=path, text=text, sha=content_hash(text))


def normalise(text: str) -> str:
    """CRLF/CR → LF, and exactly one trailing newline."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


def save_doc(root: Path, corpus: Corpus, path: str, new_text: str, expected_sha: str) -> SaveResult:
    """Write *new_text* to *path* if the disk still hashes to *expected_sha*."""
    target, reason = _target(root, corpus, path)
    if target is None:
        return SaveResult(ok=False, reason=reason, sha="")
    try:
        disk_bytes = target.read_bytes()
    except OSError:
        return SaveResult(ok=False, reason="unreadable", sha="")
    disk_text = _decode(disk_bytes)
    disk_sha = content_hash(disk_text)
    if disk_sha != expected_sha:
        return SaveResult(ok=False, reason="conflict", sha=disk_sha, disk_text=disk_text)

    new_norm = normalise(new_text)
    new_bytes = new_norm.encode("utf-8")
    if new_bytes == disk_bytes:
        return SaveResult(ok=True, reason="unchanged", sha=disk_sha)

    tmp_name: str | None = None
    try:
        mode = target.stat().st_mode
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(new_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
        tmp_name = None
    except OSError as exc:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        return SaveResult(ok=False, reason=f"write-failed: {exc.strerror or exc}", sha=disk_sha)
    return SaveResult(ok=True, reason=None, sha=content_hash(new_norm))
