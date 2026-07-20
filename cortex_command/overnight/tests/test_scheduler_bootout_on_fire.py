"""Darwin-gated integration test for spent-job self-bootout on fire (Task 12 / R14).

The rendered ``StartCalendarInterval`` plist block carries no ``Year`` key
that launchd honours as one-shot — launchd treats a full Y/M/D/H/M block as
an annually-recurring calendar job, so a spent fire would refire ~a year
later. The launcher's success branch (the ``started`` spawn-outcome
discriminator) must boot out its OWN ``@@LABEL@@`` via
``launchctl bootout gui/$(id -u)/<label>`` BEFORE the existing plist/launcher
self-clean, so the agent is deregistered from launchd rather than merely
losing its plist file.

This test exercises the real machinery end to end:

  1. Render the production launcher template via ``_install_launcher_script``
     (so the real ``@@LABEL@@`` substitution is under test), pointed at a stub
     ``cortex`` binary that writes ``started`` to the session's
     ``spawn-outcome`` token file (driving the launcher's success branch).
  2. Write a real ``StartCalendarInterval`` plist for a near-future minute
     whose ``ProgramArguments`` runs that launcher, and ``launchctl
     bootstrap`` it into the user's GUI domain — a genuinely registered
     launchd job.
  3. Let launchd fire it on the calendar minute.
  4. Assert the label is no longer registered: ``launchctl print
     gui/$(id -u)/<label>`` exits non-zero, proving the launcher booted out
     its own spent one-shot job.

It is ``skipif(not darwin)`` because it requires a real ``launchctl`` and a
GUI launchd domain. If ``launchctl bootstrap`` itself cannot register the
job (no GUI session, sandboxed CI), the test ``skip``s rather than failing,
since the bootout behaviour cannot be observed without a registered job.
The same reasoning covers a registered job launchd never spawns (no
stdout/stderr log files, no spawn-outcome token): newer macOS Background
Task Management can hold a freshly-added unsigned label without failing the
bootstrap, and a fire that never happens leaves the bootout unobservable —
that path ``skip``s too (first seen Darwin 25.5, 2026-07-20). A job that
DID spawn but stays registered still fails: that is the subject regressing.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend

# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="launchd self-bootout-on-fire requires a real launchctl (darwin)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label_is_registered(uid: int, label: str) -> bool:
    """Return True iff ``launchctl print gui/<uid>/<label>`` exits 0."""
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        capture_output=True,
    )
    return result.returncode == 0


def _bootout(uid: int, label: str) -> None:
    """Best-effort teardown so a flaky run never strands a registered job."""
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{label}"],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Test: a fired launcher boots out its own spent one-shot job
# ---------------------------------------------------------------------------


def test_launcher_boots_out_own_label_after_started_fire(
    tmp_path: Path,
) -> None:
    """A near-future calendar fire whose launcher hits the ``started`` branch
    deregisters its own label, so the annually-recurring job cannot refire.
    """
    uid = os.getuid()
    # Unique label so a leftover from a prior run cannot interfere.
    label = (
        "com.charleshall.cortex-command.overnight-schedule.bootout-test."
        f"{os.getpid()}.{int(time.time())}"
    )

    plist_dir = tmp_path / "cortex-overnight-launch"
    plist_dir.mkdir(parents=True, exist_ok=True)
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    plist_path = plist_dir / f"{label}.plist"
    launcher_path = plist_dir / f"launcher-{label}.sh"

    # ---- stub cortex binary: writes the `started` token, exits 0 ----
    # The launcher invokes `<cortex_bin> overnight start ...` in the
    # foreground; under --scheduled it expects `start` to write the
    # single-token spawn-outcome file. We emulate exactly that so the
    # launcher takes its `started` success branch and reaches the bootout.
    stub_cortex = tmp_path / "cortex-stub"
    stub_cortex.write_text(
        "#!/bin/bash\n"
        # ProgramArguments → launcher passes the session dir via the
        # rendered SPAWN_OUTCOME path; the stub just needs to write the
        # token at the same place the launcher reads it.
        f'printf started > "{session_dir}/spawn-outcome"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub_cortex.chmod(0o755)

    # Render the production launcher template with the stub cortex bin.
    backend = MacOSLaunchAgentBackend()
    monkeypatched_which = stub_cortex

    # _install_launcher_script resolves the cortex bin via _resolve_cortex_bin
    # (shutil.which("cortex")); point that at our stub for this render.
    import cortex_command.overnight.scheduler.macos as macos_mod

    orig_resolve = macos_mod._resolve_cortex_bin
    macos_mod._resolve_cortex_bin = lambda: str(monkeypatched_which)
    try:
        backend._install_launcher_script(
            launcher_path=launcher_path,
            plist_path=plist_path,
            session_dir_=session_dir,
            label=label,
            session_id="bootout-test-session",
            repo_root=tmp_path,
        )
    finally:
        macos_mod._resolve_cortex_bin = orig_resolve

    assert launcher_path.exists(), "launcher template did not render"
    rendered = launcher_path.read_text(encoding="utf-8")
    assert label in rendered, "label marker was not substituted into launcher"
    # The bootout must be present and key off the launcher's own LABEL.
    assert "launchctl bootout" in rendered, "launcher missing self-bootout call"

    # ---- real plist: near-future calendar fire that runs the launcher ----
    fire_at = datetime.now() + timedelta(minutes=1, seconds=15)
    plist = {
        "Label": label,
        "ProgramArguments": [str(launcher_path), str(tmp_path), label],
        "RunAtLoad": False,
        "StartCalendarInterval": {
            "Year": fire_at.year,
            "Month": fire_at.month,
            "Day": fire_at.day,
            "Hour": fire_at.hour,
            "Minute": fire_at.minute,
        },
        "StandardOutPath": str(session_dir / "launchd-stdout.log"),
        "StandardErrorPath": str(session_dir / "launchd-stderr.log"),
    }
    with plist_path.open("wb") as fh:
        plistlib.dump(plist, fh)

    # ---- bootstrap (register) the agent into the GUI domain ----
    bootstrap = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
        capture_output=True,
    )
    if bootstrap.returncode != 0:
        pytest.skip(
            "launchctl bootstrap could not register the job in this "
            f"environment (exit {bootstrap.returncode}, "
            f"stderr={bootstrap.stderr.decode(errors='replace')!r}); "
            "cannot observe self-bootout without a registered job"
        )

    try:
        # The job must be registered immediately after bootstrap.
        assert _label_is_registered(uid, label), (
            "job not registered after bootstrap"
        )

        # ---- let launchd fire it on the calendar minute ----
        # Wait until the launcher has fired (it writes the spawn-outcome
        # token) and then boots itself out. Poll for deregistration with a
        # generous budget: calendar fires land on the minute boundary, and
        # the launcher's foreground handshake + bootout add a few seconds.
        deadline = time.monotonic() + 150.0
        deregistered = False
        while time.monotonic() < deadline:
            if not _label_is_registered(uid, label):
                deregistered = True
                break
            time.sleep(2.0)

        if not deregistered:
            # Discriminate "the subject regressed" from "the fire never
            # happened". launchd creates the Standard{Out,Error}Path files
            # when it spawns the job, so their absence plus a missing
            # spawn-outcome token means the launcher never ran at all —
            # the bootout is unobservable (BTM hold / launchd deferral),
            # which is the bootstrap-skip's reasoning one step later.
            job_spawned = (
                (session_dir / "spawn-outcome").exists()
                or (session_dir / "launchd-stdout.log").exists()
                or (session_dir / "launchd-stderr.log").exists()
            )
            if not job_spawned:
                pytest.skip(
                    "launchd registered the job but never spawned it within "
                    "the 150s budget (no stdout/stderr log, no spawn-outcome "
                    "token) — Background Task Management can hold a fresh "
                    "unapproved label without failing bootstrap; cannot "
                    "observe self-bootout without a fire"
                )

        assert deregistered, (
            "label is still registered after its near-future fire — the "
            "launcher did not boot out its own spent one-shot job. "
            f"spawn-outcome present={ (session_dir / 'spawn-outcome').exists() }, "
            f"launchd-stderr={ (session_dir / 'launchd-stderr.log').read_text(errors='replace') if (session_dir / 'launchd-stderr.log').exists() else '<absent>' }"
        )
        # The launcher reached its success branch (wrote the token via the
        # stub) — corroborates that deregistration was the bootout path,
        # not a bootstrap that never fired.
        assert (session_dir / "spawn-outcome").exists(), (
            "spawn-outcome token absent — the launcher's started branch "
            "did not run; deregistration cannot be attributed to bootout"
        )
    finally:
        # Defensive: if the assertion failed mid-flight, ensure no real
        # launchd job is left registered on the test host.
        _bootout(uid, label)
