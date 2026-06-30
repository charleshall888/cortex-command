"""Tests for the bash launcher script's fail-marker + notification path
(Task 3 of the launchagent-scheduler migration; spec §R9 / §R13).

The launcher is a templated bash script written to
``$TMPDIR/cortex-overnight-launch/launcher-{label}.sh`` at schedule time
by :meth:`MacOSLaunchAgentBackend._install_launcher_script`. launchd
runs it at fire time. On startup-failure paths (EPERM or command-not-
found on the cortex binary), the launcher must:

  1. Write a JSON sentinel at ``<session_dir>/scheduled-fire-failed.json``
     containing ``{ts, error_class, error_text, label, session_id}``.
  2. Fire an immediate macOS notification via ``osascript``.
  3. Remove its own plist file and launcher copy from ``$TMPDIR/...``.
  4. Exit non-zero so launchd records the failure.

On the success path, the launcher invokes ``cortex overnight start
--scheduled`` in the foreground (cortex performs the
``start_new_session`` detach) and decides success from the single-token
``spawn-outcome`` discriminator (a ``started`` token), then removes the
plist + launcher. We assert the same self-cleanup invariant plus the
existence of the runner stdout/stderr log files.

Each test renders the bash template via
:meth:`MacOSLaunchAgentBackend._install_launcher_script`, with a
monkeypatched cortex-binary path that points at a tempfile shell stub
(so we can exercise EPERM / command-not-found / success without
touching the real cortex binary), then invokes the launcher with
``bash`` and asserts the on-disk side effects.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend


# ---------------------------------------------------------------------------
# Skip on non-darwin: bash is POSIX, so the launcher itself runs fine on
# Linux too. The fire-time notification path shells out to osascript via
# the ``CORTEX_OSASCRIPT`` override, which ``_stub_osascript`` points at a
# no-op stub — so these tests no longer fire a real macOS notification on
# a developer's Mac (the prior PATH-only stub could not intercept the
# launcher's absolute ``/usr/bin/osascript`` call). The darwin gate is
# retained for conservatism — these failure-path tests historically ran
# only on macOS — while the platform-agnostic discriminator-branch guards
# live in ``test_launcher_envelope.py`` (which runs everywhere the suite
# runs).
# ---------------------------------------------------------------------------

_PLATFORM_SUPPORTED = sys.platform == "darwin"


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _render_launcher(
    *,
    plist_path: Path,
    launcher_path: Path,
    session_dir: Path,
    label: str,
    session_id: str,
    cortex_bin: str,
) -> None:
    """Render the bash launcher template to ``launcher_path``.

    Patches :func:`_resolve_cortex_bin` so the launcher's
    ``@@CORTEX_BIN@@`` marker is replaced with the test-supplied stub
    path instead of whatever ``shutil.which("cortex")`` would return on
    the host.
    """
    backend = MacOSLaunchAgentBackend()
    with patch(
        "cortex_command.overnight.scheduler.macos._resolve_cortex_bin",
        return_value=cortex_bin,
    ):
        backend._install_launcher_script(
            launcher_path=launcher_path,
            plist_path=plist_path,
            session_dir_=session_dir,
            label=label,
            session_id=session_id,
            repo_root=Path("/repo"),
        )


def _write_cortex_stub(
    path: Path,
    *,
    exit_code: int = 0,
    sleep_seconds: float = 0.0,
    log_path: Path | None = None,
    spawn_outcome_token: str | None = None,
    session_dir: Path | None = None,
) -> None:
    """Write an executable shell stub that simulates the cortex binary.

    Args:
        path: Where to write the stub.
        exit_code: Exit code the stub should return.
        sleep_seconds: Optional sleep before exit (used by the success-
            path test to keep the backgrounded process alive long
            enough to assert ``ps`` membership; not required for the
            log-file-existence check).
        log_path: Optional path for the stub to touch on invocation.
            Used by the success-path test to confirm the launcher
            actually exec'd the binary (vs. silently skipping).
        spawn_outcome_token: Optional single-token discriminator the real
            ``start --scheduled`` writes to ``<session_dir>/spawn-outcome``.
            The launcher decides success/dead/advisory from THIS token
            (R6/R8), not from the stub's exit code, so the success-path
            test must emit ``started`` here to model a confirmed fire.
        session_dir: Required when ``spawn_outcome_token`` is set — the
            directory the stub writes the ``spawn-outcome`` file into.
    """
    body = [
        "#!/bin/bash",
    ]
    if log_path is not None:
        body.append(f'echo "stub-invoked $$" >> "{log_path}"')
    if spawn_outcome_token is not None:
        if session_dir is None:
            raise ValueError("session_dir is required when spawn_outcome_token is set")
        body.append(f'mkdir -p "{session_dir}"')
        body.append(
            f'printf %s {spawn_outcome_token!r} > "{session_dir / "spawn-outcome"}"'
        )
    if sleep_seconds > 0:
        body.append(f"sleep {sleep_seconds}")
    body.append(f"exit {exit_code}")
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    path.chmod(0o755)


def _stub_osascript(env: dict[str, str], extra_bin_dir: Path) -> None:
    """Point the launcher at a no-op ``osascript`` so these tests never
    fire a real macOS notification.

    The launcher invokes osascript through the ``CORTEX_OSASCRIPT``
    override (defaulting to the absolute ``/usr/bin/osascript`` in
    production); we set that override to a no-op stub. A bare ``osascript``
    on ``PATH`` cannot intercept the absolute-path call, so the override is
    the load-bearing redirect; we prepend the stub dir to ``PATH`` too for
    any bare lookups. Mutates ``env`` in place.
    """
    extra_bin_dir.mkdir(parents=True, exist_ok=True)
    osascript = extra_bin_dir / "osascript"
    osascript.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    osascript.chmod(0o755)
    env["CORTEX_OSASCRIPT"] = str(osascript)
    env["PATH"] = f"{extra_bin_dir}:{env.get('PATH', '')}"


def _run_launcher(launcher_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Execute the launcher under ``bash`` with the given env."""
    return subprocess.run(
        ["bash", str(launcher_path)],
        capture_output=True,
        env=env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Failure-path tests
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PLATFORM_SUPPORTED, "launcher tests are macOS-only")
class TestLauncherCommandNotFound(unittest.TestCase):
    """When the cortex binary path does not exist, the launcher writes a
    fail-marker with ``error_class: command_not_found`` and exits 127.
    """

    def test_command_not_found_writes_fail_marker(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s1"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            # Point at a non-existent binary path. The launcher's
            # `[ ! -x "${CORTEX_BIN}" ]` check should fire the
            # command_not_found branch.
            missing_bin = tmp / "no-such-cortex"

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s1.111",
                session_id="s1",
                cortex_bin=str(missing_bin),
            )

            env = dict(os.environ)
            _stub_osascript(env, tmp / "bin")

            result = _run_launcher(launcher_path, env)

            self.assertEqual(
                result.returncode,
                127,
                f"launcher should exit 127 on command-not-found, got "
                f"{result.returncode}; stderr={result.stderr!r}",
            )

            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertTrue(
                fail_marker.exists(),
                "fail-marker not written on command-not-found",
            )

            payload = json.loads(fail_marker.read_text(encoding="utf-8"))
            self.assertEqual(payload["error_class"], "command_not_found")
            self.assertEqual(payload["session_id"], "s1")
            self.assertEqual(
                payload["label"],
                "com.charleshall.cortex-command.overnight-schedule.s1.111",
            )
            self.assertIn("ts", payload)
            self.assertIn("error_text", payload)
            self.assertIn(str(missing_bin), payload["error_text"])

            # Self-cleanup: plist and launcher both removed.
            self.assertFalse(
                plist_path.exists(),
                "plist not removed on failure path",
            )
            self.assertFalse(
                launcher_path.exists(),
                "launcher not removed on failure path",
            )


@unittest.skipUnless(_PLATFORM_SUPPORTED, "launcher tests are macOS-only")
class TestLauncherEPerm(unittest.TestCase):
    """When the cortex binary exists but exits 1 (EPERM-equivalent
    surface from the bash perspective: the binary spawned and ran but
    surfaced a permission failure), the launcher's failure handler
    treats the spawn-side failure as the EPERM class.

    Note: launchd-fired EPERM is observed when ``setsid``/``caffeinate``
    cannot exec the cortex binary at all. That surface is reproduced in
    bash by making the spawn-side `&` background fail. The
    bash-builtin spawn rarely fails in practice; the test exercises the
    code path by making the cortex binary itself non-executable
    (chmod 0o644) so the kernel returns EPERM on exec, which `bash`
    surfaces as exit 126 on the foreground command — but the launcher
    backgrounds via `&`, so the error surfaces post-fork in the
    backgrounded child rather than in the parent's `$?`.

    To produce a deterministic EPERM-equivalent test, we substitute the
    pre-flight `[ ! -x ]` check with the test's "binary exists but is
    not executable" surface: chmod 0o644 makes the file present but
    fails the executable test, which the launcher classifies as
    command_not_found. To exercise the EPERM branch specifically, we
    instead drive ``handle_failure 1`` directly via a stub that triggers
    the launcher's bash-spawn-failed path: we stub the cortex binary as
    a directory (not a file) — `[ -x <dir> ]` returns true on macOS
    bash, but `setsid` fails to exec it with EPERM-like behavior at the
    background-fork point.

    Simplification: the cleanest deterministic test is to assert that
    when we manually simulate the EPERM exit code (by inspecting the
    handler logic via a test-only invocation path), the fail-marker
    JSON has ``error_class: EPERM``. We do this by sourcing the
    rendered launcher in a wrapper that calls ``handle_failure 1``
    directly.
    """

    def test_eperm_class_writes_fail_marker_with_eperm_class(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s1"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            cortex_bin = tmp / "cortex-stub"
            _write_cortex_stub(cortex_bin, exit_code=0)

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s2.222",
                session_id="s2",
                cortex_bin=str(cortex_bin),
            )

            env = dict(os.environ)
            _stub_osascript(env, tmp / "bin")

            # Source the launcher's function definitions and call
            # handle_failure 1 directly. This is the canonical way to
            # exercise the EPERM branch of the failure handler without
            # depending on the kernel's specific exec() error surface
            # for an unexecutable binary (which differs between
            # Apple Silicon and Intel macOS in subtle ways).
            wrapper = tmp / "wrapper.sh"
            wrapper.write_text(
                f"""#!/bin/bash
# Source the launcher in a mode where its top-level commands no-op.
# The launcher's spawn-and-cleanup path runs unconditionally, so we
# instead hand-extract just the function definitions by calling
# handle_failure before the spawn would fire. Easiest: replace the
# pre-flight test with one that sends control to handle_failure 1.

# Read the rendered launcher and rewrite the pre-flight check.
sed 's|handle_failure 127|handle_failure 1|' "{launcher_path}" > "{tmp}/launcher-eperm.sh"
chmod +x "{tmp}/launcher-eperm.sh"

# Now invoke with a non-existent binary so the [ ! -x ] check fires
# but routes to handle_failure 1 (EPERM) instead of 127.
"{tmp}/launcher-eperm.sh"
""",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            # Make the cortex binary path resolve to something that
            # fails the [ -x ] test, so the rewritten pre-flight fires.
            cortex_bin.unlink()

            result = subprocess.run(
                ["bash", str(wrapper)],
                capture_output=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(
                result.returncode,
                1,
                f"wrapper should exit 1 on EPERM branch, got "
                f"{result.returncode}; stderr={result.stderr!r}",
            )

            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertTrue(
                fail_marker.exists(),
                "fail-marker not written on EPERM branch",
            )

            payload = json.loads(fail_marker.read_text(encoding="utf-8"))
            self.assertEqual(payload["error_class"], "EPERM")
            self.assertEqual(payload["session_id"], "s2")
            self.assertIn("ts", payload)
            self.assertIn("error_text", payload)


# ---------------------------------------------------------------------------
# Success-path test
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PLATFORM_SUPPORTED, "launcher tests are macOS-only")
class TestLauncherSuccessPath(unittest.TestCase):
    """Successful spawn: stdout/stderr log files exist, plist + launcher
    are removed, no fail-marker is written, exit 0."""

    def test_success_path_creates_logs_and_removes_plist_and_launcher(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s3"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            cortex_bin = tmp / "cortex-stub"
            invocation_log = tmp / "stub-invocations.log"
            # The launcher decides success from the ``started`` token the
            # real ``start --scheduled`` writes to ``spawn-outcome`` (R6/R8),
            # NOT from the stub's exit code. Emit the token so the
            # discriminator branch resolves to the success path.
            _write_cortex_stub(
                cortex_bin,
                exit_code=0,
                sleep_seconds=2.0,
                log_path=invocation_log,
                spawn_outcome_token="started",
                session_dir=session_dir,
            )

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s3.333",
                session_id="s3",
                cortex_bin=str(cortex_bin),
            )

            env = dict(os.environ)
            _stub_osascript(env, tmp / "bin")

            result = _run_launcher(launcher_path, env)

            self.assertEqual(
                result.returncode,
                0,
                f"launcher should exit 0 on success, got "
                f"{result.returncode}; stderr={result.stderr!r}",
            )

            # Self-cleanup: plist and launcher both removed.
            self.assertFalse(
                plist_path.exists(),
                "plist not removed on success path",
            )
            self.assertFalse(
                launcher_path.exists(),
                "launcher not removed on success path",
            )

            # Log files exist (the backgrounded child redirected
            # stdout/stderr to them via the launcher's `>>` operators).
            stdout_log = session_dir / "runner-stdout.log"
            stderr_log = session_dir / "runner-stderr.log"
            self.assertTrue(
                stdout_log.exists(),
                "runner-stdout.log not created on success path",
            )
            self.assertTrue(
                stderr_log.exists(),
                "runner-stderr.log not created on success path",
            )

            # No fail-marker on success.
            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertFalse(
                fail_marker.exists(),
                "fail-marker should not be written on success path",
            )

            # Wait briefly for the backgrounded stub to log its
            # invocation (proves the cortex binary was actually exec'd
            # by the launcher, not skipped silently). The stub sleeps
            # 2s, but logs *before* sleeping, so this should be near-
            # instant.
            for _ in range(50):
                if invocation_log.exists() and invocation_log.read_text():
                    break
                time.sleep(0.05)
            self.assertTrue(
                invocation_log.exists() and invocation_log.read_text(),
                "cortex stub was not invoked by the launcher's spawn path",
            )


# ---------------------------------------------------------------------------
# JSON-shape test (rendered template + parse)
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PLATFORM_SUPPORTED, "launcher tests are macOS-only")
class TestLauncherFailMarkerJsonShape(unittest.TestCase):
    """The fail-marker file produced on the command-not-found path must
    parse cleanly via :func:`json.loads` and contain the spec-required
    fields ``ts``, ``error_class``, ``error_text``, ``label``, and
    ``session_id``.
    """

    def test_fail_marker_json_shape_is_valid(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s4"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            missing_bin = tmp / "no-such-cortex-binary"

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s4.444",
                session_id="s4",
                cortex_bin=str(missing_bin),
            )

            env = dict(os.environ)
            _stub_osascript(env, tmp / "bin")

            _run_launcher(launcher_path, env)

            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertTrue(fail_marker.exists())

            # json.loads must not raise.
            payload = json.loads(fail_marker.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict)

            # Required keys.
            for key in ("ts", "error_class", "error_text", "label", "session_id"):
                self.assertIn(key, payload, f"missing key {key!r}")

            # Field types.
            self.assertIsInstance(payload["ts"], str)
            self.assertIsInstance(payload["error_class"], str)
            self.assertIsInstance(payload["error_text"], str)
            self.assertIsInstance(payload["label"], str)
            self.assertIsInstance(payload["session_id"], str)


if __name__ == "__main__":
    unittest.main()
