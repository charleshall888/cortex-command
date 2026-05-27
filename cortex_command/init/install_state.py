"""Stdlib-only shared marker-path module for the install-in-progress state.

This module is the single source of truth for the install-in-progress marker
path used by both the cortex CLI wheel (``cortex init --ensure``, Task 4) and
the cortex-overnight plugin (``install_core.py``).  The wheel cannot import
from the plugin — ``install_core.py`` calls ``sys.exit(1)`` on import when
``CLAUDE_PLUGIN_ROOT`` is unset — so the dependency direction is
plugin → wheel.

Imports: stdlib only (``os``, ``pathlib``).
"""

from __future__ import annotations

import os
from pathlib import Path


#: Seconds after which an install-in-progress marker is considered stale
#: (catastrophic-failure safety net for SIGKILL/OOM cases, per spec R20).
INSTALL_MARKER_STALE_SECONDS: float = 600.0


def install_in_progress_marker_path() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/install.in-progress``.

    Resolved fresh on each call so tests can redirect ``XDG_STATE_HOME``
    via ``monkeypatch`` without any module-level caching.
    """
    return (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
        / "cortex-command"
        / "install.in-progress"
    )
