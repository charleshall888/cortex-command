"""Parity test: install-in-progress marker path (Task 4).

Asserts that the wheel-side canonical function
``cortex_command.init.install_state.install_in_progress_marker_path``
and the plugin-side delegating function
``plugins/cortex-overnight/install_core.py:_install_in_progress_marker_path``
return identical paths, and that each function is stable across two calls
(no mutation of the returned Path object between calls).

The plugin module is loaded via ``importlib.util.spec_from_file_location``
because the directory name contains a hyphen (not importable via normal
package syntax).  The ``CLAUDE_PLUGIN_ROOT`` env var is set to ``tmp_path``
before the module is loaded to satisfy ``install_core._enforce_plugin_root``'s
startup guard (which calls ``sys.exit(1)`` when the var is absent or when the
module file is not under the declared root).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_CORE_PATH = REPO_ROOT / "plugins" / "cortex-overnight" / "install_core.py"


def _load_install_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Load ``install_core`` as a standalone module with CLAUDE_PLUGIN_ROOT set.

    ``install_core._enforce_plugin_root()`` is called at import time and
    calls ``sys.exit(1)`` when ``CLAUDE_PLUGIN_ROOT`` is absent or when the
    module file is not under the declared root.  We set the env var to the
    *actual* plugin directory so the path-identity check passes.
    """
    plugin_dir = INSTALL_CORE_PATH.parent
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))

    # Use a unique module name so repeated test runs do not collide with a
    # cached entry in sys.modules.
    module_name = "install_core_under_test_task4"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, INSTALL_CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not create module spec for {INSTALL_CORE_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_marker_path_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wheel function and plugin function return the same path."""
    from cortex_command.init.install_state import (
        install_in_progress_marker_path as wheel_fn,
    )

    install_core = _load_install_core(tmp_path, monkeypatch)
    plugin_fn = install_core._install_in_progress_marker_path

    wheel_result = wheel_fn()
    plugin_result = plugin_fn()

    assert wheel_result == plugin_result, (
        f"Path mismatch: wheel={wheel_result!r}, plugin={plugin_result!r}"
    )


def test_marker_path_stable_across_two_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each function returns an equal path on successive calls (no mutation)."""
    from cortex_command.init.install_state import (
        install_in_progress_marker_path as wheel_fn,
    )

    install_core = _load_install_core(tmp_path, monkeypatch)
    plugin_fn = install_core._install_in_progress_marker_path

    assert wheel_fn() == wheel_fn(), "wheel_fn() is not stable across two calls"
    assert plugin_fn() == plugin_fn(), "plugin_fn() is not stable across two calls"


def test_marker_path_xdg_state_home_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting XDG_STATE_HOME redirects both functions to the new base."""
    from cortex_command.init.install_state import (
        install_in_progress_marker_path as wheel_fn,
    )

    install_core = _load_install_core(tmp_path, monkeypatch)
    plugin_fn = install_core._install_in_progress_marker_path

    fake_state = tmp_path / "xdg_state"
    monkeypatch.setenv("XDG_STATE_HOME", str(fake_state))

    expected = fake_state / "cortex-command" / "install.in-progress"

    assert wheel_fn() == expected, (
        f"wheel_fn() under custom XDG_STATE_HOME: got {wheel_fn()!r}, "
        f"expected {expected!r}"
    )
    assert plugin_fn() == expected, (
        f"plugin_fn() under custom XDG_STATE_HOME: got {plugin_fn()!r}, "
        f"expected {expected!r}"
    )
    assert wheel_fn() == plugin_fn(), (
        "Wheel and plugin diverge under custom XDG_STATE_HOME"
    )
