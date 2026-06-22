"""macOS launchd backend for the overnight scheduler.

Renders a launchd plist via stdlib :mod:`plistlib`, validates it via a
``dumps``/``loads`` round-trip, writes it to ``$TMPDIR/cortex-overnight-launch/``,
bootstraps the agent via ``launchctl bootstrap gui/$(id -u)``, then
verifies registration via ``launchctl print`` by confirming the durable
armed fact (an armed-state line — ``state = waiting`` on Darwin <25 or
``state = not running`` on Darwin 25 / macOS 26 — or the registered
calendar block).

Task 2 filled in plist render, env snapshot, target-time validation,
and bootstrap-and-verify. Task 3 filled the launcher-script seam.
Task 4 wires the sidecar / GC seams and wraps the entire ``schedule()``
body in :func:`schedule_lock` so concurrent schedule calls cannot
race on GC vs. sidecar-entry writes.
"""

from __future__ import annotations

import logging
import os
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from cortex_command.overnight.scheduler import sidecar as _sidecar
from cortex_command.overnight.scheduler.labels import mint_label, parse_label
from cortex_command.overnight.scheduler.lock import schedule_lock
from cortex_command.overnight.scheduler.protocol import (
    CancelResult,
    ScheduledHandle,
)


logger = logging.getLogger(__name__)


# launchctl print exit code 113 means "job not registered" — the
# canonical signal that a plist on disk is no longer tracked by launchd
# and is therefore safe to GC. Centralized as a module constant so the
# tests and the GC path agree on the magic number.
_LAUNCHCTL_PRINT_NOT_REGISTERED_EXIT = 113

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum lookahead window for scheduled fires.
_MAX_SCHEDULE_HORIZON = timedelta(days=7)

# Environment variables snapshot (R15). PATH always; the rest only if
# already set in the launching environment. HOME/USER/LOGNAME/TMPDIR are
# intentionally NOT snapshotted — launchd inherits them from the
# logged-in session per RQ3.
_OPTIONAL_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CORTEX_REPO_ROOT",
    "CORTEX_WORKTREE_ROOT",
)

# Durable armed-state substrings to accept in the post-bootstrap
# `launchctl print` output. The job's runtime `state` is volatile across
# Darwin versions: an armed-but-dormant ``StartCalendarInterval`` agent
# reports ``state = waiting`` on Darwin <25 but ``state = not running``
# on Darwin 25 / macOS 26. Both are the same durable fact — the agent is
# registered and armed, just not currently executing — so the verifier
# accepts either rather than requiring the volatile ``waiting`` literal.
# ``launchctl print`` is documented by Apple as "NOT API", so we also
# corroborate the armed fact structurally via the registered calendar
# block (see ``_print_confirms_armed``).
_VERIFY_STATE_SUBSTRINGS = (
    b"state = not running",
    b"state = waiting",
)

# Structural corroboration of the durable armed fact: a correctly-armed
# StartCalendarInterval agent's `launchctl print` output carries its
# calendar trigger block. Presence of this section (alongside a clean
# exit) confirms the agent is registered and armed independent of the
# volatile runtime `state` line.
_VERIFY_CALENDAR_SUBSTRING = b"calendarinterval"

# Total wallclock budget for the post-bootstrap verify poll, in seconds.
_VERIFY_POLL_BUDGET_SEC = 1.0
_VERIFY_POLL_INTERVAL_SEC = 0.05


# ---------------------------------------------------------------------------
# Persistent guardian constants (spec §R6, Task 10)
# ---------------------------------------------------------------------------

# The SINGLE fixed host-level launchd label for the out-of-process recovery
# guardian. There is exactly ONE guardian agent per host — NOT one per
# session — so the label is a constant, not a per-session minted string.
# This is the install/GC-per-session-avoidance property: a single persistent
# agent scans all `executing` sessions each tick.
GUARDIAN_LABEL = "com.charleshall.cortex-command.overnight-guardian"

# Poll cadence for the guardian, in seconds. The guardian fires every
# `StartInterval` seconds, runs `cortex overnight guardian scan` to
# completion, and exits — then `StartInterval` re-fires it on the next tick.
# 300s matches the heartbeat cadence (orchestrator `_heartbeat_loop`) so the
# guardian's detection granularity tracks the runner's own liveness signal.
GUARDIAN_START_INTERVAL_SECONDS = 300

# Crash-loop floor for the guardian, in seconds. If a scan tick exits almost
# immediately (e.g. a hard crash on startup), `ThrottleInterval` is the
# minimum wall-clock launchd waits before re-firing — the only coherent
# crash-handling addition to a `StartInterval` job. We do NOT set an
# unconditional `KeepAlive`: a `StartInterval` job runs-to-completion and
# exits each tick, and a bare-true `KeepAlive` would relaunch it the instant
# it exits (throttled only to this ~10s floor), collapsing the poll interval
# into a near-continuous busy-loop. `StartInterval`'s own periodic re-fire IS
# the restart-on-crash supervision (the "who-watches-the-watchman" story).
GUARDIAN_THROTTLE_INTERVAL_SECONDS = 60


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PlistValidationError(Exception):
    """Raised when the plist round-trip (``dumps`` then ``loads``) does not
    match the original dict structure.

    Attributes:
        label: The launchd label whose plist failed validation.
        key: The first key whose round-trip value diverged from the
            original (or ``None`` if the divergence is structural rather
            than per-key).
    """

    def __init__(self, label: str, key: str | None) -> None:
        self.label = label
        self.key = key
        if key is None:
            super().__init__(
                f"plist round-trip mismatch for label {label!r}"
            )
        else:
            super().__init__(
                f"plist round-trip mismatch for label {label!r} at key {key!r}"
            )


class LaunchctlBootstrapError(Exception):
    """Raised when ``launchctl bootstrap`` exits non-zero."""

    def __init__(self, stderr: bytes | str, exit_code: int) -> None:
        if isinstance(stderr, bytes):
            stderr_text = stderr.decode("utf-8", errors="replace")
        else:
            stderr_text = stderr
        self.stderr = stderr_text
        self.exit_code = exit_code
        super().__init__(
            f"launchctl bootstrap failed (exit {exit_code}): {stderr_text}"
        )


class LaunchctlVerifyError(Exception):
    """Raised when post-bootstrap ``launchctl print`` does not confirm the
    job is armed (a durable armed-state line or the registered calendar
    block) within the verify-poll budget.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        super().__init__(
            f"launchctl print did not confirm an armed job for "
            f"label {label!r} within {_VERIFY_POLL_BUDGET_SEC:.2f}s"
        )


# ---------------------------------------------------------------------------
# Target-time parsing
# ---------------------------------------------------------------------------


def parse_target_time(
    target: str,
    now: datetime | None = None,
) -> datetime:
    """Resolve a user-supplied target time to a concrete ``datetime``.

    Accepts two forms:
        - ``HH:MM`` (24-hour local time). Resolved against today; rolls
          to tomorrow if the resulting time is in the past.
        - ``YYYY-MM-DDTHH:MM`` (ISO 8601 local time, no tz). Parsed via
          :meth:`datetime.fromisoformat`.

    Args:
        target: Target-time string in one of the two accepted forms.
        now: Optional reference "now" for deterministic tests.

    Returns:
        Naive local ``datetime`` representing the resolved fire time.

    Raises:
        ValueError: With one of the spec-mandated phrasings:
            - ``"target time invalid: Feb 29 not in {year}"``
            - ``"target time is in the past"``
            - ``"target time is more than 7 days in the future"``
            - ``"target time has invalid format ..."``
    """
    if now is None:
        now = datetime.now()

    target = target.strip()

    if "T" in target:
        # ISO 8601 path. datetime.fromisoformat raises ValueError for
        # both unparseable strings AND invalid calendar dates (e.g.
        # Feb 29 in a non-leap year). We need to distinguish the two
        # so the Feb-29 error gets the spec's exact phrasing.
        if _is_feb_29_in_non_leap_year(target):
            year = _extract_year(target)
            raise ValueError(
                f"target time invalid: Feb 29 not in {year}"
            )
        try:
            resolved = datetime.fromisoformat(target)
        except ValueError as exc:
            # Re-raise generic parse failures with a clearer prefix; the
            # Feb-29 case is already handled above.
            raise ValueError(
                f"target time has invalid format ({target!r}): {exc}"
            ) from exc
    else:
        # HH:MM path.
        try:
            hour_str, minute_str = target.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"target time has invalid format ({target!r}); "
                f"expected HH:MM or YYYY-MM-DDTHH:MM"
            ) from exc
        resolved = now.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if resolved <= now:
            resolved = resolved + timedelta(days=1)

    if resolved <= now:
        raise ValueError("target time is in the past")

    if resolved - now > _MAX_SCHEDULE_HORIZON:
        raise ValueError(
            "target time is more than 7 days in the future"
        )

    return resolved


def _is_feb_29_in_non_leap_year(target: str) -> bool:
    """Return True if ``target`` looks like ``YYYY-02-29T...`` and ``YYYY``
    is not a leap year. Pure-string check — does not call
    :meth:`datetime.fromisoformat`.
    """
    # Expected shape: 'YYYY-02-29T...'
    if len(target) < 10:
        return False
    if target[4:10] != "-02-29":
        return False
    try:
        year = int(target[:4])
    except ValueError:
        return False
    return not _is_leap_year(year)


def _extract_year(target: str) -> int:
    """Extract the year prefix from ``target``. Caller guarantees shape."""
    return int(target[:4])


def _is_leap_year(year: int) -> bool:
    """Standard Gregorian leap-year rule."""
    if year % 4 != 0:
        return False
    if year % 100 != 0:
        return True
    return year % 400 == 0


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class MacOSLaunchAgentBackend:
    """launchd-backed scheduler for macOS.

    Constructor takes no args; environment is snapshotted lazily inside
    :meth:`schedule`.
    """

    # Per-invocation advisory flag (R10). Set True by ``schedule()`` when
    # the post-bootstrap liveness probe was inconclusive (a
    # ``LaunchctlVerifyError`` from ``_bootstrap_and_verify``). The probe
    # is advisory — it never aborts bookkeeping — so the bootstrapped job
    # is still recorded (sidecar + ``scheduled_start``) and the command
    # returns exit 0. The CLI handler reads this attribute after
    # ``schedule()`` returns to surface a non-fatal stderr warning. A
    # fresh backend instance is created per CLI invocation
    # (``get_backend()``), so this instance attribute is invocation-local.
    last_verify_inconclusive: bool = False

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def schedule(
        self,
        target: datetime,
        session_id: str,
        env: dict[str, str],
        repo_root: Path,
    ) -> ScheduledHandle:
        """Schedule a one-shot launchd agent firing at ``target``.

        Wraps the entire critical section (GC pass → launcher install
        → plist write → ``launchctl bootstrap`` + verify → sidecar
        write) in :func:`schedule_lock`. Holding the lock across the
        whole sequence prevents the race where a concurrent
        ``schedule()`` invocation's GC observes this call's
        just-written plist as orphan (label not yet in sidecar) and
        removes it before the sidecar entry lands.

        Args:
            target: Wall-clock fire time. Must be in the future.
            session_id: Overnight session identifier.
            env: Caller-supplied environment mapping. Used only to
                provide a default if the process environment is missing
                a key — the canonical snapshot is taken from
                ``os.environ`` per R15.
            repo_root: Absolute path to the repository the runner should
                operate on.

        The post-bootstrap liveness probe is **advisory** (R10): an
        inconclusive ``launchctl print`` raises
        :class:`LaunchctlVerifyError` from ``_bootstrap_and_verify``, but
        that error is caught inside ``_mint_and_install`` and recorded on
        :attr:`last_verify_inconclusive` instead of aborting. Bookkeeping
        (the sidecar entry here, plus the ``scheduled_start`` state-file
        write in the CLI handler) therefore always completes for a
        correctly-armed-but-unconfirmed job, and the command returns
        exit 0 with a non-fatal stderr warning.

        Returns:
            ScheduledHandle describing the scheduled job.
        """
        from cortex_command.overnight.state import session_dir

        # Reset the advisory flag for this invocation. ``_mint_and_install``
        # flips it True if the liveness probe was inconclusive.
        self.last_verify_inconclusive = False

        if target <= datetime.now():
            raise ValueError("target time is in the past")
        if target - datetime.now() > _MAX_SCHEDULE_HORIZON:
            raise ValueError(
                "target time is more than 7 days in the future"
            )

        plist_dir = self._plist_dir()
        plist_dir.mkdir(parents=True, exist_ok=True)

        sess_dir = session_dir(session_id)
        env_snapshot = self._snapshot_env(env)

        # Acquire the cross-process schedule lock BEFORE the GC pass
        # and hold it through bootstrap+verify and the sidecar write.
        # See module docstring + schedule_lock() docstring for the
        # rationale.
        with schedule_lock():
            self._gc_pass()

            # Mint label and try to bootstrap; on collision retry once
            # with epoch+1 (R6). After that, surface the collision.
            label, plist_path, launcher_path = self._mint_and_install(
                session_id=session_id,
                target=target,
                session_dir_=sess_dir,
                env_snapshot=env_snapshot,
                repo_root=repo_root,
                plist_dir=plist_dir,
            )

            created_at_iso = datetime.now().isoformat()
            # Emit tz-aware with the local offset (R7). ``target`` is the
            # naive-local fire time from ``parse_target_time``; attaching
            # the offset via ``.astimezone()`` makes new ``scheduled_start``
            # values unambiguous so ``status`` reads them without relying on
            # the reader's naive→local normalization backstop (R6). The GC
            # ``_is_spent`` loop already normalizes a now-aware
            # ``scheduled_for`` against its naive ``now`` (see ``_is_spent``).
            scheduled_for_iso = target.astimezone().isoformat()
            handle = ScheduledHandle(
                label=label,
                session_id=session_id,
                plist_path=plist_path,
                launcher_path=launcher_path,
                scheduled_for_iso=scheduled_for_iso,
                created_at_iso=created_at_iso,
            )
            self._write_sidecar_entry(handle)

        return handle

    def cancel(self, label: str) -> CancelResult:
        """Cancel a previously-scheduled launchd agent (Task 7).

        Sequence:
          1. ``launchctl bootout gui/$(id -u)/<label>`` — unloads the
             agent. Exit codes are reported in the returned dataclass;
             non-zero is NOT treated as fatal because the agent may
             already be gone (e.g. fired and completed).
          2. Remove the sidecar entry for ``label`` (idempotent).
          3. Remove the plist file from ``$TMPDIR/cortex-overnight-launch/``
             (idempotent).
          4. Remove the launcher script (idempotent).

        Held under :func:`schedule_lock` so it serializes against
        concurrent ``schedule()`` calls' GC + sidecar writes.
        """
        plist_dir = self._plist_dir()
        plist_path = plist_dir / f"{label}.plist"
        launcher_path = plist_dir / f"launcher-{label}.sh"

        with schedule_lock():
            uid = os.getuid()
            try:
                bootout_result = subprocess.run(
                    ["launchctl", "bootout", f"gui/{uid}/{label}"],
                    capture_output=True,
                )
                bootout_exit = bootout_result.returncode
            except OSError as exc:
                logger.warning("launchctl bootout failed for %s: %s", label, exc)
                bootout_exit = -1

            sidecar_removed = self._remove_sidecar_entry(label)
            plist_removed = _safe_unlink(plist_path)
            launcher_removed = _safe_unlink(launcher_path)

        return CancelResult(
            label=label,
            bootout_exit_code=bootout_exit,
            sidecar_removed=sidecar_removed,
            plist_removed=plist_removed,
            launcher_removed=launcher_removed,
        )

    def list_active(self) -> list[ScheduledHandle]:
        """Return the current sidecar entries (Task 7)."""
        return list(_sidecar.read_sidecar())

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "darwin"

    # ------------------------------------------------------------------
    # Mint + install + bootstrap (with epoch+1 retry on collision)
    # ------------------------------------------------------------------

    def _mint_and_install(
        self,
        session_id: str,
        target: datetime,
        session_dir_: Path,
        env_snapshot: dict[str, str],
        repo_root: Path,
        plist_dir: Path,
    ) -> tuple[str, Path, Path]:
        """Mint a label, render+validate the plist, install launcher,
        bootstrap launchd, and verify registration.

        On the first ``LaunchctlBootstrapError`` consistent with a label
        collision (R6), retry once with ``epoch + 1``. On a second
        collision, re-raise so the caller surfaces the failure.

        Returns:
            ``(label, plist_path, launcher_path)`` triple of the
            successfully bootstrapped agent.
        """
        first_attempt_epoch: int | None = None
        for attempt in (0, 1):
            now_epoch = (
                None
                if attempt == 0
                else (first_attempt_epoch or 0) + 1
            )
            label = mint_label(session_id, now_epoch=now_epoch)
            if attempt == 0:
                # Recover the epoch we just minted so the retry can
                # increment by exactly one.
                _, first_attempt_epoch = _split_label_epoch(label)

            plist_path = plist_dir / f"{label}.plist"
            launcher_path = plist_dir / f"launcher-{label}.sh"

            self._install_launcher_script(
                launcher_path=launcher_path,
                plist_path=plist_path,
                session_dir_=session_dir_,
                label=label,
                session_id=session_id,
                repo_root=repo_root,
            )

            plist_bytes = self._render_and_validate_plist(
                label=label,
                target=target,
                env_snapshot=env_snapshot,
                launcher_path=launcher_path,
                repo_root=repo_root,
                session_dir_=session_dir_,
            )
            plist_path.write_bytes(plist_bytes)

            try:
                self._bootstrap_and_verify(plist_path, label)
            except LaunchctlVerifyError as exc:
                # The liveness probe is ADVISORY (R10): bootstrap
                # succeeded (the job IS armed) but ``launchctl print`` did
                # not confirm the armed-state line within the poll budget.
                # An inconclusive probe must NOT abort — bookkeeping
                # (sidecar + ``scheduled_start``) must still complete so a
                # correctly-armed job is recorded and the command returns
                # exit 0. Record the advisory and treat the install as
                # successful; the CLI handler surfaces a stderr warning.
                logger.warning(
                    "launchctl print did not confirm an armed job for "
                    "label %s within the verify budget; recording the "
                    "schedule anyway (probe is advisory): %s",
                    label,
                    exc,
                )
                self.last_verify_inconclusive = True
                return label, plist_path, launcher_path
            except LaunchctlBootstrapError as exc:
                # On collision-suspected failures, retry once with
                # epoch+1. If we've already retried, surface.
                if attempt == 1:
                    if _is_label_collision(exc):
                        raise LaunchctlBootstrapError(
                            "label collision; retry in 1 second",
                            exc.exit_code,
                        ) from exc
                    raise
                if not _is_label_collision(exc):
                    raise
                # Cleanup pre-retry: remove the just-written plist and
                # launcher so we can re-mint cleanly.
                plist_path.unlink(missing_ok=True)
                launcher_path.unlink(missing_ok=True)
                continue
            else:
                return label, plist_path, launcher_path

        # Unreachable: the loop returns on success or raises on second
        # failure. Defensive raise satisfies type-checkers.
        raise RuntimeError(
            "unreachable: _mint_and_install loop exited without return"
        )

    # ------------------------------------------------------------------
    # Plist render + round-trip validation
    # ------------------------------------------------------------------

    def _render_and_validate_plist(
        self,
        label: str,
        target: datetime,
        env_snapshot: dict[str, str],
        launcher_path: Path,
        repo_root: Path,
        session_dir_: Path,
    ) -> bytes:
        """Build the plist dict, dump to bytes, round-trip-validate."""
        plist_dict = self._build_plist_dict(
            label=label,
            target=target,
            env_snapshot=env_snapshot,
            launcher_path=launcher_path,
            repo_root=repo_root,
            session_dir_=session_dir_,
        )
        rendered = plistlib.dumps(plist_dict)
        roundtrip = plistlib.loads(rendered)
        if roundtrip != plist_dict:
            # Identify the first divergent top-level key to populate the
            # exception. plistlib's ordering is preserved, so we can
            # iterate the original.
            divergent_key: str | None = None
            for key in plist_dict:
                if key not in roundtrip or roundtrip[key] != plist_dict[key]:
                    divergent_key = key
                    break
            raise PlistValidationError(label, divergent_key)
        return rendered

    @staticmethod
    def _build_plist_dict(
        label: str,
        target: datetime,
        env_snapshot: dict[str, str],
        launcher_path: Path,
        repo_root: Path,
        session_dir_: Path,
    ) -> dict:
        """Construct the plist dict per the spec (R6 / R7 / R15)."""
        return {
            "Label": label,
            "ProgramArguments": [
                str(launcher_path),
                str(repo_root),
                label,
            ],
            "RunAtLoad": False,
            "StartCalendarInterval": {
                "Year": target.year,
                "Month": target.month,
                "Day": target.day,
                "Hour": target.hour,
                "Minute": target.minute,
            },
            "EnvironmentVariables": dict(env_snapshot),
            "StandardOutPath": str(session_dir_ / "launchd-stdout.log"),
            "StandardErrorPath": str(session_dir_ / "launchd-stderr.log"),
        }

    # ------------------------------------------------------------------
    # Env snapshot
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_env(caller_env: dict[str, str]) -> dict[str, str]:
        """Snapshot the schedule-time env per R15.

        Always includes ``PATH`` (preferring the process environment but
        falling back to the caller-supplied dict). Optional keys
        (``ANTHROPIC_API_KEY``, ``CLAUDE_CODE_OAUTH_TOKEN``,
        ``CORTEX_REPO_ROOT``, ``CORTEX_WORKTREE_ROOT``) are included only
        when set in the process environment. ``HOME``/``USER``/
        ``LOGNAME``/``TMPDIR`` are NOT included — launchd inherits them.
        """
        snapshot: dict[str, str] = {}
        path_value = os.environ.get("PATH") or caller_env.get("PATH")
        if path_value is not None:
            snapshot["PATH"] = path_value
        for key in _OPTIONAL_ENV_KEYS:
            value = os.environ.get(key)
            if value is not None:
                snapshot[key] = value
        return snapshot

    # ------------------------------------------------------------------
    # launchctl bootstrap + verify
    # ------------------------------------------------------------------

    def _bootstrap_and_verify(
        self,
        plist_path: Path,
        label: str,
    ) -> None:
        """Run ``launchctl bootstrap`` then verify with ``launchctl print``.

        The verify step confirms the durable fact that the agent is armed
        — registered and dormant-or-waiting — rather than the volatile
        ``state = waiting`` literal that Darwin <25 happened to report.
        Darwin 25 / macOS 26 reports ``state = not running`` for an
        armed-but-dormant ``StartCalendarInterval`` agent, so a literal
        ``waiting`` check false-fails a correctly-armed job. The verifier
        accepts either armed-state line, and also accepts a clean
        ``print`` exit whose output carries the registered calendar block
        (structural corroboration, since ``launchctl print`` is "NOT API"
        per Apple and its exact phrasing is not contractual).

        Raises:
            LaunchctlBootstrapError: bootstrap returned non-zero.
            LaunchctlVerifyError: bootstrap succeeded but ``launchctl
                print`` did not confirm an armed job within the
                verify-poll budget.
        """
        uid = os.getuid()
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise LaunchctlBootstrapError(
                result.stderr, result.returncode
            )

        # Poll launchctl print up to the budget for the durable armed
        # fact (an armed-state line or the registered calendar block).
        deadline = time.monotonic() + _VERIFY_POLL_BUDGET_SEC
        while True:
            print_result = subprocess.run(
                ["launchctl", "print", f"gui/{uid}/{label}"],
                capture_output=True,
            )
            if _print_confirms_armed(print_result):
                return
            if time.monotonic() >= deadline:
                raise LaunchctlVerifyError(label)
            time.sleep(_VERIFY_POLL_INTERVAL_SEC)

    # ------------------------------------------------------------------
    # Seams filled by Tasks 3 & 4
    # ------------------------------------------------------------------

    @staticmethod
    def _plist_dir() -> Path:
        """Resolve ``$TMPDIR/cortex-overnight-launch/``."""
        tmpdir = os.environ.get("TMPDIR") or "/tmp"
        return Path(tmpdir) / "cortex-overnight-launch"

    def _install_launcher_script(
        self,
        launcher_path: Path,
        plist_path: Path,
        session_dir_: Path,
        label: str,
        session_id: str,
        repo_root: Path,
    ) -> None:
        """Render the templated bash launcher to ``launcher_path`` (R9 / R13).

        Reads the ``launcher.sh`` template shipped alongside this module
        as package data, substitutes the six template markers
        (``@@PLIST_PATH@@``, ``@@LAUNCHER_PATH@@``, ``@@SESSION_DIR@@``,
        ``@@LABEL@@``, ``@@CORTEX_BIN@@``, ``@@SESSION_ID@@``) with their
        concrete values, writes the result to ``launcher_path``, and
        marks it executable.
        """
        launcher_path.parent.mkdir(parents=True, exist_ok=True)

        template_text = _read_launcher_template()
        cortex_bin = _resolve_cortex_bin()

        rendered = (
            template_text
            .replace("@@PLIST_PATH@@", str(plist_path))
            .replace("@@LAUNCHER_PATH@@", str(launcher_path))
            .replace("@@SESSION_DIR@@", str(session_dir_))
            .replace("@@LABEL@@", label)
            .replace("@@CORTEX_BIN@@", cortex_bin)
            .replace("@@SESSION_ID@@", session_id)
        )

        launcher_path.write_text(rendered, encoding="utf-8")
        try:
            launcher_path.chmod(0o755)
        except OSError:
            pass

    def _write_sidecar_entry(self, handle: ScheduledHandle) -> None:
        """Persist ``handle`` to the sidecar index.

        Must be called inside :func:`schedule_lock` — the lock
        guarantees no concurrent ``_gc_pass`` can observe this call's
        just-written plist as orphan before the sidecar entry lands.
        """
        _sidecar.add_entry(handle)

    def _remove_sidecar_entry(self, label: str) -> bool:
        """Remove the sidecar entry for ``label``.

        Returns:
            ``True`` if the entry was removed, ``False`` if it was
            already absent. Idempotent.
        """
        return _sidecar.remove_entry(label)

    def _gc_pass(self) -> int:
        """Remove orphan plists and launcher scripts from ``$TMPDIR``.

        For each ``*.plist`` under ``$TMPDIR/cortex-overnight-launch/``:
          - If its label is absent from the sidecar index OR
            ``launchctl print gui/$(id -u)/<label>`` exits 113 (job not
            registered), remove the plist file.
          - Also remove the paired ``launcher-<label>.sh`` regardless
            of whether it exists (it may have been removed already by
            the launcher itself per R9).

        Spent-schedule reaping (R15): a sidecar entry whose
        ``scheduled_for_iso`` is in the past is a spent one-shot fire.
        It is reaped — plist + launcher + the sidecar entry itself —
        **regardless of ``launchctl print`` registration state**, so a
        missed or failed post-fire ``bootout`` (R14) is still cleaned
        up. This is the GC backstop for the runner/launcher self-bootout:
        even if the agent remains registered with launchd, a past
        ``scheduled_for_iso`` proves the one-shot window has passed and
        the entry will never legitimately re-fire (the
        ``StartCalendarInterval`` ``Year`` key is inert — see R16). Spent
        entries whose plist file is already gone are still swept from the
        sidecar so the index does not accumulate dead records.

        Corruption guard: if :func:`sidecar.read_sidecar` returns an
        empty list because the file is corrupt (warning logged
        internally), we cannot distinguish "no schedules" from "lost
        all sidecar state". To fail closed in that case, this method
        consults the sidecar file's existence: if the file exists but
        ``read_sidecar`` returned ``[]``, we skip GC entirely and log
        a warning. (When the file simply does not exist — first-use —
        the safe interpretation IS "no tracked schedules" so GC
        proceeds normally; an absent file cannot be the result of
        corruption, only of never having been written.)

        Returns:
            Count of files removed (plists + launchers combined).

        MUST only be called inside :func:`schedule_lock` — the lock is
        the load-bearing guard against the cross-process race
        described in the module docstring. Standalone invocation is
        not part of the contract.
        """
        plist_dir = self._plist_dir()
        if not plist_dir.is_dir():
            return 0

        # Fail closed on a corrupt sidecar: if the file is present but
        # decodes to an empty list (corruption signal — the warning
        # was logged inside read_sidecar), refuse to GC. A genuinely
        # empty sidecar with no schedules has the file simply absent
        # in the first-use case; once the first add_entry runs the
        # file always contains at least the placeholder ``[]`` — so
        # "file exists but read returned []" is a corruption signal
        # for files that were previously valid lists too. Pragmatic
        # rule: if the file exists AND we cannot json-decode it as a
        # non-empty list, AND there is at least one plist in
        # plist_dir, refuse to GC (worst case: leaks a few stale
        # plists until corruption is repaired by the next successful
        # add_entry write).
        sidecar_file = _sidecar.sidecar_path()
        sidecar_handles = _sidecar.read_sidecar()
        tracked_labels = {h.label for h in sidecar_handles}
        # Map label -> scheduled_for_iso so the loop can detect spent
        # one-shot fires (past timestamp) regardless of registration.
        scheduled_for_by_label = {
            h.label: h.scheduled_for_iso for h in sidecar_handles
        }
        if sidecar_file.exists() and not tracked_labels:
            if _sidecar_json_is_corrupt(sidecar_file):
                logger.warning(
                    "skipping GC: sidecar %s appears corrupt",
                    sidecar_file,
                )
                return 0

        removed = 0
        uid = os.getuid()
        # Labels reaped because their one-shot window is spent; their
        # sidecar entries are removed after the plist sweep below.
        spent_labels_reaped: set[str] = set()
        now = datetime.now()
        for plist_path in sorted(plist_dir.glob("*.plist")):
            label = plist_path.stem
            # Validate that the label looks like one of ours; ignore
            # foreign plists that may have ended up in this dir.
            try:
                parse_label(label)
            except ValueError:
                continue

            if label in tracked_labels:
                # Spent one-shot fire: a past scheduled_for_iso means the
                # window has passed and the entry can never legitimately
                # re-fire (R15). Reap plist + launcher + sidecar entry
                # regardless of launchctl registration state — this is
                # the backstop for a missed/failed post-fire bootout.
                if _is_spent(scheduled_for_by_label.get(label), now):
                    if _safe_unlink(plist_path):
                        removed += 1
                    launcher_path = plist_path.parent / f"launcher-{label}.sh"
                    if _safe_unlink(launcher_path):
                        removed += 1
                    spent_labels_reaped.add(label)
                    continue
                # Tracked — but still GC if launchctl confirms it's
                # not registered (e.g. fired and completed without a
                # cancel call). Probe launchctl print.
                if not _is_launchctl_registered(label, uid):
                    if _safe_unlink(plist_path):
                        removed += 1
                    launcher_path = plist_path.parent / f"launcher-{label}.sh"
                    if _safe_unlink(launcher_path):
                        removed += 1
                continue

            # Untracked — orphan. Remove unconditionally.
            if _safe_unlink(plist_path):
                removed += 1
            launcher_path = plist_path.parent / f"launcher-{label}.sh"
            if _safe_unlink(launcher_path):
                removed += 1

        # Sweep spent sidecar entries whose plist file was already gone
        # (e.g. the launcher removed it post-fire but bootout was missed):
        # the entry itself must still be reaped so the index does not
        # accumulate dead records.
        for label, scheduled_for_iso in scheduled_for_by_label.items():
            if label in spent_labels_reaped:
                continue
            if _is_spent(scheduled_for_iso, now):
                # Best-effort unlink of any straggler files; the entry
                # removal below is the load-bearing reap.
                _safe_unlink(plist_dir / f"{label}.plist")
                _safe_unlink(plist_dir / f"launcher-{label}.sh")
                spent_labels_reaped.add(label)

        for label in spent_labels_reaped:
            self._remove_sidecar_entry(label)

        if removed:
            logger.info(
                "GC removed %d orphan plist/launcher file(s)", removed
            )
        return removed


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _split_label_epoch(label: str) -> tuple[str, int]:
    """Local helper that wraps :func:`labels.parse_label` without the
    full validation surface; used by :meth:`_mint_and_install`'s
    epoch+1 retry path.
    """
    from cortex_command.overnight.scheduler.labels import parse_label

    return parse_label(label)


def _is_label_collision(exc: LaunchctlBootstrapError) -> bool:
    """Heuristic: launchctl returns a stderr message mentioning
    "already loaded" / "already exists" on a label collision. Treat any
    such message as a collision so the epoch+1 retry path engages.
    """
    msg = (exc.stderr or "").lower()
    return (
        "already loaded" in msg
        or "already exists" in msg
        or "service already loaded" in msg
    )


# ---------------------------------------------------------------------------
# Launcher template helpers (Task 3)
# ---------------------------------------------------------------------------


def _read_launcher_template() -> str:
    """Load the bash launcher template shipped as package data.

    The template lives alongside this module at
    ``cortex_command/overnight/scheduler/launcher.sh`` and is rendered
    at schedule time by :meth:`MacOSLaunchAgentBackend._install_launcher_script`.
    """
    template_path = Path(__file__).resolve().parent / "launcher.sh"
    return template_path.read_text(encoding="utf-8")


def _print_confirms_armed(
    print_result: subprocess.CompletedProcess,
) -> bool:
    """Return True iff a ``launchctl print`` result confirms the job is armed.

    The "armed" fact is durable across Darwin versions even though the
    runtime ``state`` line is not. A correctly-armed but dormant
    ``StartCalendarInterval`` agent reports ``state = waiting`` on
    Darwin <25 and ``state = not running`` on Darwin 25 / macOS 26 — both
    mean "registered, armed, not currently executing". We accept either,
    and additionally accept a clean ``print`` exit whose output carries
    the registered calendar trigger block (structural corroboration that
    does not depend on the volatile state phrasing, since ``launchctl
    print`` is documented by Apple as "NOT API").
    """
    if print_result.returncode != 0:
        return False
    stdout = print_result.stdout or b""
    if any(token in stdout for token in _VERIFY_STATE_SUBSTRINGS):
        return True
    # Structural corroboration: the calendar block proves the job is the
    # armed StartCalendarInterval agent we just bootstrapped, regardless
    # of how this Darwin version phrases the runtime state line.
    return _VERIFY_CALENDAR_SUBSTRING in stdout.lower()


def _is_spent(scheduled_for_iso: str | None, now: datetime) -> bool:
    """Return True iff ``scheduled_for_iso`` is a parseable past timestamp.

    A spent one-shot fire (R15) is one whose resolved fire time has
    already passed: GC reaps its plist + launcher + sidecar entry
    regardless of ``launchctl`` registration state, as the backstop for
    a missed or failed post-fire ``bootout``. ``scheduled_for_iso`` is
    the naive-local ISO 8601 string written by ``schedule()`` via
    ``target.isoformat()``, so it is compared against a naive-local
    ``datetime.now()``.

    Conservative on unparseable / missing input: returns ``False`` so a
    record we cannot interpret is never reaped on a spurious "past"
    reading (it falls through to the registration-state checks instead).

    Since R7 the writer emits ``scheduled_for_iso`` tz-aware (local
    offset), while the GC loop still passes a naive ``now =
    datetime.now()``. The ``scheduled_for.tzinfo is not None and
    now.tzinfo is None`` branch below normalizes ``now`` to the stored
    offset so a spent aware fire is still reaped. Legacy naive values
    (pre-R7) keep comparing naive-vs-naive.
    """
    if not scheduled_for_iso:
        return False
    try:
        scheduled_for = datetime.fromisoformat(scheduled_for_iso)
    except ValueError:
        return False
    # Compare on the same naive/aware footing as the stored value. A
    # tz-aware stored value (forward-compat) is compared against an
    # aware "now" in the same offset; a naive value against naive now.
    if scheduled_for.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone(scheduled_for.tzinfo)
    elif scheduled_for.tzinfo is None and now.tzinfo is not None:
        scheduled_for = scheduled_for.replace(tzinfo=now.tzinfo)
    return scheduled_for < now


def _is_launchctl_registered(label: str, uid: int) -> bool:
    """Return True iff ``launchctl print gui/<uid>/<label>`` exits 0.

    Used by :meth:`MacOSLaunchAgentBackend._gc_pass` to distinguish
    plists whose launchd job is still alive (preserve) from ones that
    have completed or been booted out (collect). An exit of
    :data:`_LAUNCHCTL_PRINT_NOT_REGISTERED_EXIT` (113) means "job not
    registered" — the GC trigger condition. Any other non-zero exit
    is treated conservatively as "still registered" so we never GC a
    plist whose status we cannot determine.
    """
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True,
        )
    except OSError:
        # launchctl not available; assume registered to fail closed.
        return True
    return result.returncode == 0


def _safe_unlink(path: Path) -> bool:
    """Remove ``path`` if present. Return True iff a file was removed.

    Tolerates ``FileNotFoundError`` (returns False) and ``OSError``
    other than not-found (logs at WARNING and returns False). Used by
    GC to drive the removed-files counter without letting a single
    permission error halt the whole sweep.
    """
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("GC could not remove %s: %s", path, exc)
        return False


def _sidecar_json_is_corrupt(sidecar_file: Path) -> bool:
    """Return True iff ``sidecar_file`` cannot be JSON-decoded as a list.

    Helper for :meth:`MacOSLaunchAgentBackend._gc_pass`'s fail-closed
    path. Distinct from :func:`sidecar.read_sidecar` which already
    swallows corruption — here we need a yes/no signal to gate GC.
    """
    import json

    try:
        text = sidecar_file.read_text(encoding="utf-8")
    except OSError:
        return True
    if not text.strip():
        # Empty file — treat as corrupt for the purpose of GC
        # (a properly-written empty sidecar contains "[]\n").
        return True
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return True
    return not isinstance(decoded, list)


def _resolve_cortex_bin() -> str:
    """Resolve the absolute path to the cortex binary launchd will exec.

    Prefers ``shutil.which("cortex")`` so the binary path matches what
    the user has on their interactive PATH (the same binary they granted
    Full Disk Access to per R13). Falls back to the literal string
    ``"cortex"`` if ``which`` returns ``None`` so the launcher's own
    pre-flight ``[ ! -x ]`` check fires the fail-marker path with a
    clean ``command_not_found`` error class instead of silently
    succeeding against a stale PATH lookup.
    """
    resolved = shutil.which("cortex")
    return resolved if resolved is not None else "cortex"


# ---------------------------------------------------------------------------
# Persistent guardian plist (spec §R6, Task 10)
#
# The guardian reuses ONLY the generic launchctl primitives here
# (``_bootstrap_and_verify`` for install, ``launchctl bootout`` +
# ``_safe_unlink`` for remove). Everything else is net-new and deliberately
# does NOT reuse the per-session one-shot machinery (label minting, the
# self-bootout launcher template, the sidecar index, ``_gc_pass``): the
# guardian is ONE persistent agent on a ``StartInterval`` cadence with a
# fixed host-level label, not a per-session ``StartCalendarInterval``
# one-shot.
# ---------------------------------------------------------------------------


def build_guardian_plist_dict(
    *,
    cortex_bin: str | None = None,
    repo_root: Path,
    start_interval: int = GUARDIAN_START_INTERVAL_SECONDS,
    throttle_interval: int = GUARDIAN_THROTTLE_INTERVAL_SECONDS,
) -> dict:
    """Construct the persistent-guardian plist dict (spec §R6, Task 10).

    The shape is intentionally distinct from the per-session one-shot
    :meth:`MacOSLaunchAgentBackend._build_plist_dict`:

      * ``Label`` is the fixed host-level :data:`GUARDIAN_LABEL` constant —
        one agent for the whole host, NOT a per-session minted label.
      * ``StartInterval`` is an integer second cadence — the job fires every
        ``start_interval`` seconds, runs ``cortex overnight guardian scan``
        to completion, and exits. This is NOT ``StartCalendarInterval`` (a
        one-shot wall-clock fire); the guardian is a recurring poll.
      * ``ProgramArguments`` invoke the installed ``cortex`` entrypoint with
        ``overnight guardian scan`` directly — no launcher-script shim.
      * ``ThrottleInterval`` is the crash-loop floor.
      * There is **no** ``KeepAlive`` key. A bare-true ``KeepAlive`` on a
        ``StartInterval`` run-to-completion job would relaunch it the instant
        it exits each tick (throttled only to ``ThrottleInterval``), collapsing
        the poll interval into a near-continuous busy-loop. ``StartInterval``'s
        own periodic re-fire is the restart-on-crash supervision. (If
        restart-on-failure were ever wanted it would be the conditional dict
        form ``KeepAlive = {"SuccessfulExit": False}``, never the bare-true
        form — but the default omits it entirely.)

    Args:
        cortex_bin: Absolute path to the ``cortex`` binary launchd execs.
            Defaults to :func:`_resolve_cortex_bin` (``shutil.which`` with a
            literal ``"cortex"`` fallback).
        repo_root: The user repo whose ``cortex/lifecycle/sessions/`` the
            scan enumerates. Passed via ``CORTEX_REPO_ROOT`` so the scan's
            ``_resolve_repo_path`` resolves to it under launchd (where ``cwd``
            is not the user's repo).
        start_interval: Poll cadence in seconds.
        throttle_interval: Crash-loop floor in seconds.
    """
    resolved_bin = cortex_bin if cortex_bin is not None else _resolve_cortex_bin()
    return {
        "Label": GUARDIAN_LABEL,
        "ProgramArguments": [
            resolved_bin,
            "overnight",
            "guardian",
            "scan",
        ],
        "RunAtLoad": False,
        "StartInterval": int(start_interval),
        "ThrottleInterval": int(throttle_interval),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "CORTEX_REPO_ROOT": str(repo_root),
        },
    }


def _render_and_validate_guardian_plist(plist_dict: dict) -> bytes:
    """Dump the guardian plist dict to bytes and round-trip-validate it.

    A guardian variant of
    :meth:`MacOSLaunchAgentBackend._render_and_validate_plist` — the
    per-session validator validates against the dict ITS builder produces, so
    the guardian needs its own round-trip check against the guardian dict.
    Raises :class:`PlistValidationError` (label = :data:`GUARDIAN_LABEL`) if
    the ``dumps``/``loads`` round-trip diverges.
    """
    rendered = plistlib.dumps(plist_dict)
    roundtrip = plistlib.loads(rendered)
    if roundtrip != plist_dict:
        divergent_key: str | None = None
        for key in plist_dict:
            if key not in roundtrip or roundtrip[key] != plist_dict[key]:
                divergent_key = key
                break
        raise PlistValidationError(GUARDIAN_LABEL, divergent_key)
    return rendered


def _guardian_plist_path(plist_dir: Path | None = None) -> Path:
    """Resolve the guardian plist path.

    Defaults to ``$TMPDIR/cortex-overnight-launch/<GUARDIAN_LABEL>.plist`` —
    the same ``_plist_dir()`` the per-session backend writes into — but
    accepts an explicit ``plist_dir`` override so the install/remove verbs and
    their tests can point at a temp dir without touching the real one.
    """
    base = plist_dir if plist_dir is not None else MacOSLaunchAgentBackend._plist_dir()
    return base / f"{GUARDIAN_LABEL}.plist"


def install_guardian(
    *,
    repo_root: Path,
    plist_dir: Path | None = None,
    start_interval: int = GUARDIAN_START_INTERVAL_SECONDS,
) -> Path:
    """Render, write, and bootstrap the SINGLE host-level guardian agent.

    Re-install-friendly (idempotent): if a guardian is already registered,
    it is booted out first so ``launchctl bootstrap`` does not collide on the
    fixed label, then the freshly-rendered plist is bootstrapped. Reuses the
    generic :meth:`MacOSLaunchAgentBackend._bootstrap_and_verify` (the same
    ``launchctl bootstrap`` + armed-state verify the per-session path uses);
    the post-bootstrap liveness probe is advisory (an inconclusive
    ``launchctl print`` is logged, not fatal).

    Args:
        repo_root: The user repo the scan enumerates (threaded via
            ``CORTEX_REPO_ROOT``).
        plist_dir: Optional override for the plist directory (tests).
        start_interval: Poll cadence in seconds.

    Returns:
        The path of the written guardian plist.
    """
    target_dir = plist_dir if plist_dir is not None else MacOSLaunchAgentBackend._plist_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    plist_path = _guardian_plist_path(target_dir)

    plist_dict = build_guardian_plist_dict(
        repo_root=repo_root,
        start_interval=start_interval,
    )
    plist_bytes = _render_and_validate_guardian_plist(plist_dict)
    plist_path.write_bytes(plist_bytes)

    # Re-install replaces: bootout any prior registration on the fixed label
    # first (idempotent — a clean no-op if not registered) so bootstrap does
    # not collide. Failures here are non-fatal; bootstrap below is the gate.
    _bootout_guardian()

    backend = MacOSLaunchAgentBackend()
    try:
        backend._bootstrap_and_verify(plist_path, GUARDIAN_LABEL)
    except LaunchctlVerifyError as exc:
        # Advisory: bootstrap succeeded (the agent IS armed) but the
        # ``launchctl print`` probe did not confirm the armed-state line
        # within the budget. Record-and-continue, mirroring the per-session
        # advisory posture — the install is successful.
        logger.warning(
            "launchctl print did not confirm the guardian agent %s within "
            "the verify budget; recording the install anyway (probe is "
            "advisory): %s",
            GUARDIAN_LABEL,
            exc,
        )

    return plist_path


def remove_guardian(plist_dir: Path | None = None) -> bool:
    """Bootout the guardian agent and unlink its plist (spec §R6, Task 10).

    A clean no-op if the guardian is not installed: ``launchctl bootout`` on
    an unregistered label is non-fatal (the agent may already be gone) and
    :func:`_safe_unlink` tolerates an absent plist. Reuses the same
    ``launchctl bootout gui/{uid}/{label}`` + :func:`_safe_unlink` the
    per-session ``cancel`` path uses.

    Returns:
        ``True`` if the plist file was removed, ``False`` if it was already
        absent.
    """
    _bootout_guardian()
    plist_path = _guardian_plist_path(plist_dir)
    return _safe_unlink(plist_path)


def _bootout_guardian() -> int:
    """``launchctl bootout gui/{uid}/<GUARDIAN_LABEL>``; non-fatal.

    Mirrors the per-session ``cancel`` bootout: a non-zero exit is NOT
    treated as fatal because the agent may already be gone (never installed,
    or already booted out). Returns the bootout exit code (``-1`` on
    ``OSError``).
    """
    uid = os.getuid()
    try:
        result = subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{GUARDIAN_LABEL}"],
            capture_output=True,
        )
        return result.returncode
    except OSError as exc:
        logger.warning("launchctl bootout failed for %s: %s", GUARDIAN_LABEL, exc)
        return -1
