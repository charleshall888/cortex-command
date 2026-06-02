"""Phase-2 regression guards for the launcher's discriminator branch (R6, R7).

The launchd launcher decides success/dead/advisory from the ROBUST
DISCRIMINATOR — the single-token ``<session_dir>/spawn-outcome`` file that
``cortex overnight start --scheduled`` writes (Task 4) — NOT from the
process exit code. Under ``--scheduled``, ``start`` returns exit 1 for
BOTH a genuinely-dead fire (``spawn_died``) and a live-but-unconfirmed
fire (``spawn_unconfirmed``), so an exit-code→error_class mapping would
discard the real failure class. These tests pin that the launcher:

  * (a) ``spawn_died`` token → writes ``scheduled-fire-failed.json`` with
    the REAL ``error_class`` (``spawn_died``, NOT the legacy ``EPERM``);
  * (b) ``spawn_unconfirmed`` token → writes a DISTINCT advisory
    (non-failure) marker carrying a ``kind``/``severity`` field, and does
    NOT write a failure marker;
  * (c) ``started`` token + exit 1 → does NOT write a failure marker
    (the discriminator, not the exit code, decides success).

These are platform-agnostic: they render the real launcher template and
run it under ``bash`` with a stub ``CORTEX_BIN`` that writes a canned
``spawn-outcome`` token and exits 1. ``bash`` is POSIX; the only
macOS-only surface the launcher touches on the failure path is
``osascript``, which we stub on ``PATH`` (the launcher calls it as
``/usr/bin/osascript`` best-effort with output suppressed and ``|| true``,
so its absence is harmless — but we stub it for cleanliness on non-darwin
where ``/usr/bin/osascript`` does not exist).

They run via ``just test`` anywhere the suite runs. They are NOT wired
into GitHub Actions today (``validate.yml`` runs only skill + callgraph
validators); CI-wiring is an out-of-scope follow-up.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend


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
    """Render the real bash launcher template to ``launcher_path``.

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


def _write_token_stub(
    path: Path,
    *,
    token: str,
    exit_code: int,
    session_dir: Path,
    write_runner_pid: bool = False,
) -> None:
    """Write an executable shell stub that simulates ``cortex … start --scheduled``.

    The real ``start`` writes the single-token ``spawn-outcome``
    discriminator under ``--scheduled``; this stub fakes that side effect
    by writing ``token`` to ``<session_dir>/spawn-outcome`` and then
    exiting with ``exit_code`` (1 for both the dead and advisory cases,
    matching production). It ignores its argv (the launcher passes
    ``overnight start --state … --format json --force --scheduled``).
    """
    spawn_outcome = session_dir / "spawn-outcome"
    body = [
        "#!/bin/bash",
        f'mkdir -p "{session_dir}"',
        f'printf %s {token!r} > "{spawn_outcome}"',
    ]
    if write_runner_pid:
        body.append(f'printf %s "$$" > "{session_dir / "runner.pid"}"')
    body.append(f"exit {exit_code}")
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    path.chmod(0o755)


def _stub_osascript_in_path(extra_bin_dir: Path) -> str:
    """Drop a no-op ``osascript`` stub on PATH so the launcher's
    notification call does not fail (or fire a real notification) during
    tests. Returns the modified PATH string.
    """
    extra_bin_dir.mkdir(parents=True, exist_ok=True)
    osascript = extra_bin_dir / "osascript"
    osascript.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    osascript.chmod(0o755)
    return f"{extra_bin_dir}:{os.environ.get('PATH', '')}"


def _run_launcher(
    launcher_path: Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Execute the launcher under ``bash`` with the given env."""
    return subprocess.run(
        ["bash", str(launcher_path)],
        capture_output=True,
        env=env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# (a) spawn_died token → failure marker with the REAL error_class
# ---------------------------------------------------------------------------


class TestLauncherSpawnDiedWritesFailureMarker(unittest.TestCase):
    """A ``spawn_died`` token (with ``start`` exit 1) writes a failure
    marker whose ``error_class`` is the real class from the discriminator,
    NOT the legacy exit-code→``EPERM`` mapping.
    """

    def test_spawn_died_token_writes_failure_marker_with_real_class(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s1"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            cortex_bin = tmp / "cortex-stub"
            _write_token_stub(
                cortex_bin,
                token="spawn_died",
                exit_code=1,
                session_dir=session_dir,
            )

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s1.111",
                session_id="s1",
                cortex_bin=str(cortex_bin),
            )

            env = dict(os.environ)
            env["PATH"] = _stub_osascript_in_path(tmp / "bin")

            result = _run_launcher(launcher_path, env)

            # A genuine dead fire exits non-zero so launchd records it.
            self.assertNotEqual(
                result.returncode,
                0,
                f"dead fire should exit non-zero; stderr={result.stderr!r}",
            )

            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertTrue(
                fail_marker.exists(),
                "failure marker not written on spawn_died token",
            )

            payload = json.loads(fail_marker.read_text(encoding="utf-8"))
            # The REAL class from the discriminator — NOT the legacy EPERM.
            self.assertEqual(
                payload["error_class"],
                "spawn_died",
                f"failure marker should carry the real spawn_died class, got "
                f"{payload['error_class']!r}",
            )
            self.assertNotEqual(
                payload["error_class"],
                "EPERM",
                "legacy exit-code→EPERM mapping must not fire post-start",
            )
            self.assertEqual(payload["session_id"], "s1")
            self.assertEqual(
                payload["label"],
                "com.charleshall.cortex-command.overnight-schedule.s1.111",
            )
            self.assertIn("ts", payload)
            self.assertIn("error_text", payload)

            # No advisory marker on the dead path.
            advisory = session_dir / "scheduled-fire-advisory.json"
            self.assertFalse(
                advisory.exists(),
                "advisory marker should not be written on a dead fire",
            )

            # Self-cleanup still happens.
            self.assertFalse(plist_path.exists(), "plist not removed")
            self.assertFalse(launcher_path.exists(), "launcher not removed")


# ---------------------------------------------------------------------------
# (b) spawn_unconfirmed token → distinct advisory (non-failure) marker
# ---------------------------------------------------------------------------


class TestLauncherSpawnUnconfirmedWritesAdvisoryMarker(unittest.TestCase):
    """A ``spawn_unconfirmed`` token (with ``start`` exit 1) writes a
    DISTINCT advisory marker carrying a ``kind``/``severity`` field, NOT a
    failure marker.
    """

    def test_spawn_unconfirmed_token_writes_advisory_not_failure(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s2"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            cortex_bin = tmp / "cortex-stub"
            _write_token_stub(
                cortex_bin,
                token="spawn_unconfirmed",
                exit_code=1,
                session_dir=session_dir,
            )

            _render_launcher(
                plist_path=plist_path,
                launcher_path=launcher_path,
                session_dir=session_dir,
                label="com.charleshall.cortex-command.overnight-schedule.s2.222",
                session_id="s2",
                cortex_bin=str(cortex_bin),
            )

            env = dict(os.environ)
            env["PATH"] = _stub_osascript_in_path(tmp / "bin")

            result = _run_launcher(launcher_path, env)

            # A live-but-slow fire is NOT a failure: exit 0.
            self.assertEqual(
                result.returncode,
                0,
                f"advisory (live-but-slow) fire should exit 0; "
                f"stderr={result.stderr!r}",
            )

            # NO failure marker.
            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertFalse(
                fail_marker.exists(),
                "failure marker must NOT be written on spawn_unconfirmed",
            )

            # A DISTINCT advisory marker, carrying a kind/severity field.
            advisory = session_dir / "scheduled-fire-advisory.json"
            self.assertTrue(
                advisory.exists(),
                "advisory marker not written on spawn_unconfirmed token",
            )

            payload = json.loads(advisory.read_text(encoding="utf-8"))
            # The advisory is marked non-failure via a kind/severity field.
            self.assertEqual(
                payload.get("kind"),
                "advisory",
                f"advisory marker must carry kind=advisory, got {payload!r}",
            )
            self.assertEqual(
                payload.get("severity"),
                "advisory",
                f"advisory marker must carry severity=advisory, got {payload!r}",
            )
            self.assertEqual(payload["session_id"], "s2")
            self.assertEqual(
                payload["label"],
                "com.charleshall.cortex-command.overnight-schedule.s2.222",
            )
            self.assertIn("ts", payload)

            # Self-cleanup still happens.
            self.assertFalse(plist_path.exists(), "plist not removed")
            self.assertFalse(launcher_path.exists(), "launcher not removed")


# ---------------------------------------------------------------------------
# (c) started token + exit 1 → NO failure marker (discriminator decides)
# ---------------------------------------------------------------------------


class TestLauncherStartedTokenIgnoresExitCode(unittest.TestCase):
    """A ``started`` token decides success even if ``start`` exits 1 — the
    discriminator, not the process exit code, drives the decision. No
    failure marker is written.
    """

    def test_started_token_with_exit_1_writes_no_failure_marker(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            session_dir = tmp / "sessions" / "s3"
            session_dir.mkdir(parents=True)

            plist_path = tmp / "launch" / "fake.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("<plist/>", encoding="utf-8")

            launcher_path = tmp / "launch" / "launcher.sh"

            cortex_bin = tmp / "cortex-stub"
            # ``started`` token but exit 1 — proves the launcher keys off
            # the token, not the exit code.
            _write_token_stub(
                cortex_bin,
                token="started",
                exit_code=1,
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
            env["PATH"] = _stub_osascript_in_path(tmp / "bin")

            result = _run_launcher(launcher_path, env)

            # A started fire is a success regardless of the exit code.
            self.assertEqual(
                result.returncode,
                0,
                f"started token should yield exit 0 even when start exits 1; "
                f"stderr={result.stderr!r}",
            )

            # No failure marker.
            fail_marker = session_dir / "scheduled-fire-failed.json"
            self.assertFalse(
                fail_marker.exists(),
                "failure marker must NOT be written on a started token",
            )

            # No advisory marker either — this was a confirmed success.
            advisory = session_dir / "scheduled-fire-advisory.json"
            self.assertFalse(
                advisory.exists(),
                "advisory marker must NOT be written on a started token",
            )

            # Self-cleanup still happens.
            self.assertFalse(plist_path.exists(), "plist not removed")
            self.assertFalse(launcher_path.exists(), "launcher not removed")


if __name__ == "__main__":
    unittest.main()
