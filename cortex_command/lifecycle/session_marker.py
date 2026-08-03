"""The one place that reads and writes a lifecycle's session-owner marker.

A lifecycle directory records which Claude Code session owns it in a marker file
holding that session's id. Three call sites resolved it independently and had
already drifted apart: ``discovery`` read ``.session`` **and** the chain-migrated
``.session-owner``, while critical-review's residue writer globbed ``.session``
only, and ``enter`` was the sole writer. That divergence is why a refine-phase
critical review lost its findings — see :func:`resolve_features_by_session`.

The marker is **local and per-machine**: the ``cortex init`` gitignore template
carries ``cortex/lifecycle/**/.session`` and ``**/.session-owner``, and nothing
here may cause it to be committed.
"""

from __future__ import annotations

import os
from pathlib import Path

# Both marker names, newest first. ``.session-owner`` is the chain-migrated
# spelling; a resolver that reads only one of them silently misses lifecycles
# written by the other writer.
MARKER_NAMES = (".session", ".session-owner")

_ARCHIVE_DIRNAME = "archive"

# The files whose presence makes a directory under ``cortex/lifecycle/`` a real
# feature rather than an infrastructure sibling.
_FEATURE_ARTIFACTS = (
    "events.log",
    "index.md",
    "research.md",
    "spec.md",
    "plan.md",
    "review.md",
)

SESSION_ID_ENV = "LIFECYCLE_SESSION_ID"


def session_id_from_env() -> str:
    """Return the ambient session id (``LIFECYCLE_SESSION_ID``), or ``""``.

    The SessionStart hook (``hooks/cortex-scan-lifecycle.sh``) injects it.
    """
    return os.environ.get(SESSION_ID_ENV, "").strip()


def write_session(root: Path, feature: str, session_id: str) -> Path:
    """Record *session_id* as the owner of ``{root}/cortex/lifecycle/{feature}``.

    Writes the canonical ``.session`` name. Creating the directory is deliberate:
    the phase verbs that call this also seed ``events.log`` there.
    """
    path = root / "cortex" / "lifecycle" / feature / MARKER_NAMES[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_id, encoding="utf-8")
    return path


def resolve_features_by_session(root: Path, session_id: str) -> list[str]:
    """Return the lifecycle slugs whose marker holds *session_id*, sorted.

    Empty ``session_id`` (or no ``cortex/lifecycle/``) yields ``[]``. Unreadable
    markers are skipped rather than raised on. ``archive/`` is not a lifecycle.

    A slug is returned at most once even when both marker names are present and
    agree.

    Callers must distinguish the two empty cases themselves — "this session owns
    no lifecycle" and "a lifecycle exists but no marker names this session" are
    different failures, and only the second is a defect. Reporting them as one
    told an operator standing inside a populated lifecycle that there was *no
    active lifecycle context*, which is how a refine-phase critical review could
    drop four findings at exit 0.
    """
    if not session_id:
        return []
    lifecycle_dir = root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return []
    found: list[str] = []
    try:
        candidates = sorted(lifecycle_dir.iterdir())
    except OSError:
        return []
    for candidate in candidates:
        if not candidate.is_dir() or candidate.name == _ARCHIVE_DIRNAME:
            continue
        for marker_name in MARKER_NAMES:
            marker = candidate / marker_name
            if not marker.is_file():
                continue
            try:
                content = marker.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content == session_id:
                found.append(candidate.name)
                break
    return found


def has_any_lifecycle(root: Path) -> bool:
    """True when ``cortex/lifecycle/`` holds at least one feature directory.

    Lets a caller tell "no lifecycle at all" (a conversation-context run, which
    legitimately skips) from "lifecycles exist but none is marked with this
    session id" (an unowned lifecycle, which is a real gap worth naming).

    A feature directory is identified **positively, by its artifacts**, not by
    excluding known infrastructure names. ``cortex/lifecycle/`` also holds
    ``sessions/`` (telemetry, created as an import side effect, so it can exist
    in a repo that has never run a lifecycle), ``deferred/`` and ``archive/`` —
    and a name denylist would have to grow with every new sibling. Requiring a
    real artifact means a new infrastructure directory is inert here by default:
    getting this wrong reports ``unowned`` for a repo with no lifecycles at all,
    which is precisely the misleading-diagnosis failure this arm exists to end.
    """
    lifecycle_dir = root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return False
    try:
        candidates = list(lifecycle_dir.iterdir())
    except OSError:
        return False
    for candidate in candidates:
        if not candidate.is_dir() or candidate.name == _ARCHIVE_DIRNAME:
            continue
        if any((candidate / name).is_file() for name in _FEATURE_ARTIFACTS):
            return True
        if any((candidate / name).is_file() for name in MARKER_NAMES):
            return True
    return False
