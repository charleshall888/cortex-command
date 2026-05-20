"""Hook integration tests for ``claude/hooks/cortex-session-start-path-bootstrap.sh``.

Invokes the bash hook via subprocess with controlled stdin and PATH overrides
to exercise the skip-predicates and the additionalContext-emit path.

The integration test is best-effort because claude-code#16538 affects the
plugin-hook pipeline (where Claude Code consumes the hook's output), NOT the
hook's own emission — so the test verifies the hook emits additionalContext
correctly, but cannot verify Claude Code receives it.

Cortex-shape gate: the hook exits 0 silently when $CWD/cortex/lifecycle/ does
not exist. All fixtures that reach the self-test path must contain that subdir.

The AUGMENTED_PATH built by the hook is:
  ``$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}``

So placing a python3 shim in ``$HOME/.local/bin/`` makes it the first python3
found by the hook's ``PATH="$AUGMENTED_PATH" python3 ...`` invocation.

Coverage:
  (A) Main path: PATH excludes an expected entry -> stdout contains
      additionalContext, exit 0, no sentinel file at cortex/.cache/path-selftest.json
  (B) CORTEX_DEV_MODE=1 -> no additionalContext in stdout, exit 0
  (C) CWD/pyproject.toml names cortex-command -> no additionalContext, exit 0
  (D) PATH=/nonexistent -> hook exits 0 with empty stdout (python3 not
      reachable; self-test is silently skipped by the hook's ``|| true`` guard)
  (E) importlib.metadata.PackageNotFoundError simulation -> exit 0 silently
      (the self-test module swallows all exceptions and returns 0)
  (F) Non-cortex-shaped fixture -> hook exits 0, stdout empty (cortex-shape gate)
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "claude" / "hooks" / "cortex-session-start-path-bootstrap.sh"

# Minimal system PATH providing bash, jq, and standard utilities.
_SYSTEM_PATH = "/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin"

# Real python3 interpreter from the current process (guaranteed importable).
_PYTHON3_REAL = sys.executable


# ---------------------------------------------------------------------------
# Shim driver templates
#
# The hook builds AUGMENTED_PATH = "$HOME/.local/bin:$HOME/.cargo/bin:..."
# so a python3 shim placed in $HOME/.local/bin/ is resolved first when the
# hook runs ``PATH="$AUGMENTED_PATH" python3 -m cortex_command.doctor.path_self_test``.
# ---------------------------------------------------------------------------

_ADVISORY_SHIM_DRIVER = """\
import sys
import unittest.mock
import cortex_command.doctor.path_self_test as psm

def _fake_get_expected():
    return {"cortex-selftest-missing-entry"}

def _fake_find_missing(expected):
    return sorted(expected)

with unittest.mock.patch.object(psm, "_get_expected_entry_points", _fake_get_expected):
    with unittest.mock.patch.object(psm, "_find_missing", _fake_find_missing):
        with unittest.mock.patch.object(psm, "_should_skip", return_value=False):
            rc = psm.main()
            sys.exit(rc)
"""

_PACKAGE_NOT_FOUND_SHIM_DRIVER = """\
import sys
import unittest.mock
from importlib.metadata import PackageNotFoundError
import cortex_command.doctor.path_self_test as psm

def _raising_eps(**kwargs):
    raise PackageNotFoundError("cortex-command")

with unittest.mock.patch("importlib.metadata.entry_points", side_effect=_raising_eps):
    with unittest.mock.patch.object(psm, "_should_skip", return_value=False):
        rc = psm.main()
        sys.exit(rc)
"""


def _write_python3_shim(
    home_dir: Path,
    driver_path: Path,
) -> None:
    """Install a python3 shim in ``home_dir/.local/bin/`` that intercepts
    path_self_test invocations and delegates to ``driver_path``.

    Non-path_self_test invocations pass through to the real interpreter.
    """
    local_bin = home_dir / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    shim = local_bin / "python3"
    shim.write_text(
        f"#!/bin/bash\n"
        f'if [[ "$*" == *"path_self_test"* ]]; then\n'
        f'  exec {_PYTHON3_REAL} {driver_path}\n'
        f"else\n"
        f'  exec {_PYTHON3_REAL} "$@"\n'
        f"fi\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cortex_fixture(tmp_path: Path) -> Path:
    """Return a temp dir that satisfies the cortex-shape gate.

    Contains cortex/lifecycle/ subdir so the hook does not exit early.
    """
    fixture = tmp_path / "repo"
    fixture.mkdir()
    (fixture / "cortex" / "lifecycle").mkdir(parents=True)
    return fixture


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    """Return a temp dir used as HOME for hook subprocess calls."""
    d = tmp_path / "fake-home"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run_hook(
    cwd_fixture: Path,
    fake_home_dir: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the hook with a SessionStart JSON payload pointing at ``cwd_fixture``.

    HOME is set to ``fake_home_dir``; PATH is set to ``_SYSTEM_PATH``.
    The hook's AUGMENTED_PATH will prepend ``fake_home_dir/.local/bin`` so any
    python3 shim placed there is resolved first.

    ``extra_env`` is merged after stripping CORTEX_DEV_MODE so test cases
    control that variable explicitly.
    """
    payload = json.dumps(
        {
            "hook_event_name": "SessionStart",
            "session_id": "test-hook-integ-001",
            "cwd": str(cwd_fixture),
        }
    )

    env = os.environ.copy()
    env.pop("CORTEX_DEV_MODE", None)
    env["HOME"] = str(fake_home_dir)
    env["PATH"] = _SYSTEM_PATH
    env.pop("CLAUDE_ENV_FILE", None)

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


# ---------------------------------------------------------------------------
# (A) Main path: missing entry on PATH -> additionalContext emitted
# ---------------------------------------------------------------------------


def test_hook_emits_additional_context_for_missing_entry(
    cortex_fixture: Path,
    fake_home: Path,
    tmp_path: Path,
) -> None:
    """Hook emits additionalContext JSON when a cortex entry is absent from PATH.

    A python3 shim is installed at ``$HOME/.local/bin/python3`` (the first
    entry in AUGMENTED_PATH the hook builds) so it intercepts the hook's
    ``python3 -m cortex_command.doctor.path_self_test`` call and runs a
    controlled driver that always reports one missing entry.
    """
    driver = tmp_path / "advisory_driver.py"
    driver.write_text(_ADVISORY_SHIM_DRIVER, encoding="utf-8")
    _write_python3_shim(fake_home, driver)

    result = _run_hook(cortex_fixture, fake_home)

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert "additionalContext" in result.stdout, (
        f"expected 'additionalContext' in stdout; got: {result.stdout!r}"
    )
    assert "cortex-selftest-missing-entry" in result.stdout, (
        f"missing entry name absent from stdout: {result.stdout!r}"
    )

    # Validate stdout is parseable JSON with the expected envelope structure.
    try:
        envelope = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        pytest.fail(f"stdout is not valid JSON: {exc!r}\nstdout={result.stdout!r}")
    assert "hookSpecificOutput" in envelope, (
        f"JSON missing hookSpecificOutput key: {envelope!r}"
    )
    hook_out = envelope["hookSpecificOutput"]
    assert "additionalContext" in hook_out, (
        f"hookSpecificOutput missing additionalContext: {hook_out!r}"
    )

    # No sentinel file should be written (the module writes none).
    sentinel = cortex_fixture / "cortex" / ".cache" / "path-selftest.json"
    assert not sentinel.exists(), f"unexpected sentinel file at {sentinel}"


# ---------------------------------------------------------------------------
# (B) CORTEX_DEV_MODE=1 -> no additionalContext
# ---------------------------------------------------------------------------


def test_hook_dev_mode_no_advisory(
    cortex_fixture: Path,
    fake_home: Path,
    tmp_path: Path,
) -> None:
    """CORTEX_DEV_MODE=1 causes the self-test to skip; stdout is empty.

    A shim is installed that would emit an advisory when _should_skip() is
    False, so any emission proves the predicate was not respected.  But the
    shim still lets the real CORTEX_DEV_MODE check fire: it does NOT patch
    _should_skip; it only forces a fake missing entry if the module proceeds
    past the skip guard.
    """
    # Driver: does NOT patch _should_skip. Only patches _get_expected_entry_points
    # and _find_missing so that, if the real _should_skip() doesn't fire, we
    # would see an advisory.
    dev_mode_driver = """\
import sys
import unittest.mock
import cortex_command.doctor.path_self_test as psm

def _fake_get_expected():
    return {"cortex-selftest-missing-entry"}

def _fake_find_missing(expected):
    return sorted(expected)

with unittest.mock.patch.object(psm, "_get_expected_entry_points", _fake_get_expected):
    with unittest.mock.patch.object(psm, "_find_missing", _fake_find_missing):
        rc = psm.main()
        sys.exit(rc)
"""
    driver = tmp_path / "dev_mode_driver.py"
    driver.write_text(dev_mode_driver, encoding="utf-8")
    _write_python3_shim(fake_home, driver)

    result = _run_hook(
        cortex_fixture,
        fake_home,
        extra_env={"CORTEX_DEV_MODE": "1"},
    )

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert "additionalContext" not in result.stdout, (
        f"additionalContext unexpectedly present with CORTEX_DEV_MODE=1; "
        f"stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# (C) CWD/pyproject.toml names cortex-command -> no additionalContext
# ---------------------------------------------------------------------------


def test_hook_source_tree_no_advisory(
    cortex_fixture: Path,
    fake_home: Path,
    tmp_path: Path,
) -> None:
    """When CWD/pyproject.toml identifies the cortex-command source tree,
    the self-test skips and stdout is empty.

    The module checks ``os.getcwd()`` for a pyproject.toml whose name line
    matches ``^name\\s*=\\s*"cortex-command"``.  The test runner's CWD is the
    repo root, which has exactly such a pyproject.toml — so the real module
    (invoked via the real python3 with no skip-predicate override) correctly
    fires the source-tree predicate and emits nothing.

    A shim is still installed that would emit an advisory if the predicate
    did NOT fire (i.e. if _should_skip() returned False), making the assertion
    meaningful rather than vacuously true.
    """
    source_tree_driver = """\
import sys
import unittest.mock
import cortex_command.doctor.path_self_test as psm

def _fake_get_expected():
    return {"cortex-selftest-missing-entry"}

def _fake_find_missing(expected):
    return sorted(expected)

with unittest.mock.patch.object(psm, "_get_expected_entry_points", _fake_get_expected):
    with unittest.mock.patch.object(psm, "_find_missing", _fake_find_missing):
        rc = psm.main()
        sys.exit(rc)
"""
    driver = tmp_path / "source_tree_driver.py"
    driver.write_text(source_tree_driver, encoding="utf-8")
    _write_python3_shim(fake_home, driver)

    # The test runner's CWD is the repo root, which already has a pyproject.toml
    # that names "cortex-command".  The module's _is_cortex_command_source_tree()
    # reads os.getcwd() and fires the skip predicate.
    result = _run_hook(cortex_fixture, fake_home)

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert "additionalContext" not in result.stdout, (
        f"additionalContext unexpectedly present in source-tree fixture; "
        f"stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# (D) python3 not reachable -> hook exits 0 with empty stdout
# ---------------------------------------------------------------------------


def test_hook_exits_0_with_empty_stdout_when_python3_unreachable(
    cortex_fixture: Path,
    fake_home: Path,
) -> None:
    """When python3 is not on AUGMENTED_PATH, the hook's ``|| true`` guard
    swallows the ENOENT and the hook still exits 0 with empty stdout.

    We achieve this by using a fake_home with NO .local/bin/python3, and
    setting PATH to an empty dir so no python3 is reachable at all.
    """
    import tempfile

    # Use a path that has bash and jq but no python3.
    # Create an empty bin dir that precedes /opt/homebrew/bin in PATH.
    with tempfile.TemporaryDirectory(dir=str(fake_home)) as empty_dir:
        result = _run_hook(
            cortex_fixture,
            fake_home,
            extra_env={"PATH": f"{empty_dir}:/usr/bin:/bin"},
        )

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    # No advisory should be emitted because python3 was not reachable.
    assert "additionalContext" not in result.stdout, (
        f"additionalContext unexpectedly present when python3 is absent; "
        f"stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# (E) importlib.metadata.PackageNotFoundError simulation -> exit 0 silently
# ---------------------------------------------------------------------------


def test_hook_exits_0_when_package_not_found(
    cortex_fixture: Path,
    fake_home: Path,
    tmp_path: Path,
) -> None:
    """When importlib.metadata raises PackageNotFoundError, the self-test
    catches the exception and exits 0 silently.
    """
    driver = tmp_path / "pnf_driver.py"
    driver.write_text(_PACKAGE_NOT_FOUND_SHIM_DRIVER, encoding="utf-8")
    _write_python3_shim(fake_home, driver)

    result = _run_hook(cortex_fixture, fake_home)

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert "additionalContext" not in result.stdout, (
        f"additionalContext unexpectedly present when PackageNotFoundError raised; "
        f"stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# (F) Non-cortex-shaped fixture -> hook exits 0, stdout empty
# ---------------------------------------------------------------------------


def test_hook_exits_0_for_non_cortex_fixture(
    tmp_path: Path,
    fake_home: Path,
) -> None:
    """When cortex/lifecycle/ does not exist, the hook exits 0 silently
    without reaching the self-test invocation.
    """
    non_cortex = tmp_path / "non-cortex"
    non_cortex.mkdir()
    # No cortex/lifecycle/ subdir — hook should exit at the shape gate.

    result = _run_hook(non_cortex, fake_home)

    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout == "", (
        f"expected empty stdout for non-cortex-shaped fixture; "
        f"got: {result.stdout!r}"
    )
