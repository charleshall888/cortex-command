"""Task 11 (spec R8) — cortex-core SessionStart background-install healer.

Unit-level coverage of ``plugins/cortex-core/install_core.py``'s four skip
predicates and the dry-run initiate path. Per the task's verification note,
the *actual* SessionStart async reinstall is driven by a real session and is
NOT exercised end-to-end here — CI validates the decision logic
(skip predicates + drift comparison + would-initiate argv) via a dry-run that
stops short of the real ``uv`` spawn.

The module is loaded by absolute path under a unique module name to avoid a
``sys.path`` collision with the sibling ``plugins/cortex-overnight/install_core.py``.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "cortex-core"
MODULE_PATH = PLUGIN_ROOT / "install_core.py"


def _load_module() -> ModuleType:
    """Load cortex-core's install_core.py by path (collision-free name)."""
    spec = importlib.util.spec_from_file_location(
        "cortex_core_install_core", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install_core = _load_module()


@pytest.fixture()
def state(monkeypatch, tmp_path: Path) -> Path:
    """Redirect XDG_STATE_HOME + CLAUDE_PLUGIN_ROOT into a tmp sandbox.

    Also pins CLI_PIN to a known tag so drift is deterministic, and clears
    the opt-out / dry-run env vars each test may set explicitly.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    # CLAUDE_PLUGIN_ROOT must point at the real plugin dir so
    # _enforce_plugin_root() (the file is under it) passes.
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
    monkeypatch.delenv("CORTEX_AUTO_INSTALL", raising=False)
    monkeypatch.delenv("CORTEX_INSTALL_DRY_RUN", raising=False)
    monkeypatch.setattr(install_core, "CLI_PIN", ("v9.9.9", "2.0"))
    state_dir = tmp_path / "cortex-command"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _stub_probe(monkeypatch, version):
    """Force ``_probe_installed_version`` to return ``version`` (or None)."""
    monkeypatch.setattr(
        install_core, "_probe_installed_version", lambda: version
    )


def _forbid_spawn(monkeypatch):
    """Make any real ``subprocess.Popen`` a hard test failure.

    Guards against a regression where the dry-run/skip paths accidentally
    reach the real spawn. Only the explicit initiate-non-dry-run test opts
    into a recording stub.
    """
    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("real subprocess.Popen must not run in this test")

    monkeypatch.setattr(install_core.subprocess, "Popen", _boom)


# ---------------------------------------------------------------------------
# Skip predicate 1 — CORTEX_AUTO_INSTALL=0
# ---------------------------------------------------------------------------


def test_skip_auto_install_disabled(monkeypatch, state):
    monkeypatch.setenv("CORTEX_AUTO_INSTALL", "0")
    _forbid_spawn(monkeypatch)
    # Even with drift available, the opt-out short-circuits first.
    _stub_probe(monkeypatch, "0.0.1")
    result = install_core.run_install_in_background()
    assert result == {"action": "skipped", "reason": "auto_install_disabled"}


# ---------------------------------------------------------------------------
# Skip predicate 2 — probe failure
# ---------------------------------------------------------------------------


def test_skip_probe_failure(monkeypatch, state):
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, None)  # binary absent / bad JSON / non-zero
    result = install_core.run_install_in_background()
    assert result == {"action": "skipped", "reason": "probe_failure"}


def test_probe_returns_none_on_bad_json(monkeypatch):
    """The real probe helper maps unparseable stdout to None (predicate 2)."""

    class _Result:
        returncode = 0
        stdout = "not json{"

    monkeypatch.setattr(
        install_core.subprocess, "run", lambda *a, **k: _Result()
    )
    assert install_core._probe_installed_version() is None


# ---------------------------------------------------------------------------
# Skip predicate 3 — recent session-install-failed sentinel
# ---------------------------------------------------------------------------


def test_skip_recent_failure_sentinel(monkeypatch, state):
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")  # drift present
    sentinel = state / f"session-install-failed.{int(time.time())}"
    sentinel.write_text("prior failure", encoding="utf-8")
    result = install_core.run_install_in_background()
    assert result["action"] == "skipped"
    assert result["reason"] == "recent_failure_sentinel"
    assert result["sentinel"] == str(sentinel)


def test_stale_failure_sentinel_does_not_throttle(monkeypatch, state):
    """A sentinel older than the 30-min window is ignored (dry-run proceeds)."""
    monkeypatch.setenv("CORTEX_INSTALL_DRY_RUN", "1")
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")
    stale = state / "session-install-failed.1"  # epoch 1 → ancient
    stale.write_text("old", encoding="utf-8")
    import os

    os.utime(stale, (1, 1))
    result = install_core.run_install_in_background()
    assert result["action"] == "initiated"


# ---------------------------------------------------------------------------
# Skip predicate 4 — install-in-progress marker
# ---------------------------------------------------------------------------


def test_skip_install_in_progress(monkeypatch, state):
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")  # drift present
    marker = state / "install.in-progress"
    marker.write_text("", encoding="utf-8")  # fresh mtime
    result = install_core.run_install_in_background()
    assert result == {"action": "skipped", "reason": "install_in_progress"}


def test_stale_marker_does_not_skip(monkeypatch, state):
    """A marker older than 600s is stale and does not block (dry-run proceeds)."""
    monkeypatch.setenv("CORTEX_INSTALL_DRY_RUN", "1")
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")
    marker = state / "install.in-progress"
    marker.write_text("", encoding="utf-8")
    import os

    old = time.time() - (install_core._INSTALL_MARKER_STALE_SECONDS + 60)
    os.utime(marker, (old, old))
    result = install_core.run_install_in_background()
    assert result["action"] == "initiated"


# ---------------------------------------------------------------------------
# No-drift and dry-run initiate path
# ---------------------------------------------------------------------------


def test_no_drift_is_noop(monkeypatch, state):
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "9.9.9")  # == CLI_PIN[0] sans leading v
    result = install_core.run_install_in_background()
    assert result["action"] == "noop"
    assert result["reason"] == "no_drift"


def test_dry_run_initiate_reports_argv_without_spawning(monkeypatch, state):
    """Drift + dry-run → structured initiate outcome, no real spawn, no marker."""
    monkeypatch.setenv("CORTEX_INSTALL_DRY_RUN", "1")
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")  # drift vs v9.9.9
    result = install_core.run_install_in_background()
    assert result["action"] == "initiated"
    assert result["dry_run"] is True
    assert result["target"] == "v9.9.9"
    argv = result["argv"]
    assert "--refresh-package" in argv and "cortex-command" in argv
    assert (
        "git+https://github.com/charleshall888/cortex-command.git@v9.9.9"
        in argv
    )
    # Dry-run must not have written the in-progress marker.
    assert not (state / "install.in-progress").exists()


def test_dry_run_via_param_overrides_env(monkeypatch, state):
    """Explicit dry_run=True works even when the env var is unset."""
    _forbid_spawn(monkeypatch)
    _stub_probe(monkeypatch, "0.0.1")
    result = install_core.run_install_in_background(dry_run=True)
    assert result["action"] == "initiated" and result["dry_run"] is True


# ---------------------------------------------------------------------------
# Real initiate path — spawn is mocked (records argv/env), marker lifecycle
# ---------------------------------------------------------------------------


def test_initiate_spawns_detached_and_cleans_marker(monkeypatch, state):
    """Non-dry-run drift → Popen invoked with the pinned argv + UV_NO_PROGRESS,
    detached (start_new_session), and the marker unlinked in ``finally``."""
    _stub_probe(monkeypatch, "0.0.1")
    recorded = {}

    def _fake_popen(argv, **kwargs):  # noqa: ANN001, ANN003
        recorded["argv"] = argv
        recorded["kwargs"] = kwargs
        # The marker must exist at spawn time (written under the lock before
        # Popen). Capture its presence for the assertion below.
        recorded["marker_present_at_spawn"] = (
            state / "install.in-progress"
        ).exists()

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(install_core.subprocess, "Popen", _fake_popen)
    result = install_core.run_install_in_background()

    assert result["action"] == "initiated"
    assert result["dry_run"] is False
    assert recorded["marker_present_at_spawn"] is True
    assert recorded["kwargs"].get("start_new_session") is True
    assert recorded["kwargs"]["env"]["UV_NO_PROGRESS"] == "1"
    assert "tool" in recorded["argv"] and "install" in recorded["argv"]
    # Marker cleaned up by the finally clause after the (mocked) spawn.
    assert not (state / "install.in-progress").exists()


def test_spawn_failure_writes_sentinel(monkeypatch, state):
    """An OSError from Popen writes a session-install-failed sentinel (predicate 3
    fuel for the next session) and returns a structured failure."""
    _stub_probe(monkeypatch, "0.0.1")

    def _raise(*a, **k):  # noqa: ANN002, ANN003
        raise OSError("no such file: uv")

    monkeypatch.setattr(install_core.subprocess, "Popen", _raise)
    result = install_core.run_install_in_background()
    assert result["action"] == "failed"
    assert result["reason"] == "spawn_failure"
    sentinels = list(state.glob("session-install-failed.*"))
    assert sentinels, "spawn failure must write a session-install-failed sentinel"
    # And the marker must still have been cleaned up.
    assert not (state / "install.in-progress").exists()


# ---------------------------------------------------------------------------
# Confused-deputy guard
# ---------------------------------------------------------------------------


def test_enforce_plugin_root_rejects_absent_env(monkeypatch, state):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    with pytest.raises(SystemExit):
        install_core.run_install_in_background()


# ---------------------------------------------------------------------------
# version_tuple helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("v2.34.6", (2, 34, 6)),
        ("2.34.6", (2, 34, 6)),
        ("v1.0", (1, 0)),
        ("", ()),
    ],
)
def test_version_tuple(raw, expected):
    assert install_core.version_tuple(raw) == expected
