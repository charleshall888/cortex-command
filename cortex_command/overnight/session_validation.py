"""Session-id validation and path containment helpers.

Implements R17 security primitives shared by the ``cancel``, ``status``, and
``logs`` CLI handlers so that no command touches the filesystem with an
attacker-controlled path. Keeping these checks in one module prevents
duplicated security logic across command surfaces.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SESSION_ID_RE: re.Pattern = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")


def validate_session_id(session_id: str) -> None:
    """Raise ``ValueError('invalid session id')`` if ``session_id`` does not
    match ``SESSION_ID_RE``."""
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        raise ValueError("invalid session id")


def assert_path_contained(path: Path, root: Path) -> None:
    """Raise ``ValueError('invalid session id')`` if the real path of ``path``
    is not contained within the real path of ``root``."""
    real_path = os.path.realpath(str(path))
    real_root = os.path.realpath(str(root))
    if not real_path.startswith(real_root):
        raise ValueError("invalid session id")


def resolve_session_dir(session_id: str, lifecycle_sessions_root: Path) -> Path:
    """Validate ``session_id`` and return a contained session directory path.

    Calls :func:`validate_session_id`, computes
    ``lifecycle_sessions_root / session_id``, then asserts containment via
    :func:`assert_path_contained` before returning the path.
    """
    validate_session_id(session_id)
    session_dir = lifecycle_sessions_root / session_id
    assert_path_contained(session_dir, lifecycle_sessions_root)
    return session_dir
