"""macOS launchd backend for the overnight scheduler.

Renders a launchd plist via stdlib :mod:`plistlib`, validates it via a
``dumps``/``loads`` round-trip, writes it to ``$TMPDIR/cortex-overnight-launch/``,
bootstraps the agent via ``launchctl bootstrap gui/$(id -u)``, then
verifies registration via ``launchctl print`` (looking for the
``state = waiting`` substring).

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

# Substring to look for in the post-bootstrap `launchctl print` output.
_VERIFY_STATE_SUBSTRING = b"state = waiting"

# Total wallclock budget for the post-bootstrap verify poll, in seconds.
_VERIFY_POLL_BUDGET_SEC = 1.0
_VERIFY_POLL_INTERVAL_SEC = 0.05


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
    """Raised when post-bootstrap ``launchctl print`` does not yield
    ``state = waiting`` within the verify-poll budget.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        super().__init__(
            f"launchctl print did not report 'state = waiting' for "
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

        Returns:
            ScheduledHandle describing the scheduled job.
        """
        from cortex_command.overnight.state import session_dir

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
            scheduled_for_iso = target.isoformat()
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

        Raises:
            LaunchctlBootstrapError: bootstrap returned non-zero.
            LaunchctlVerifyError: bootstrap succeeded but the registered
                job did not appear with ``state = waiting`` within the
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

        # Poll launchctl print up to the budget for the state substring.
        deadline = time.monotonic() + _VERIFY_POLL_BUDGET_SEC
        while True:
            print_result = subprocess.run(
                ["launchctl", "print", f"gui/{uid}/{label}"],
                capture_output=True,
            )
            if (
                print_result.returncode == 0
                and _VERIFY_STATE_SUBSTRING in print_result.stdout
            ):
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
        tracked_labels = {h.label for h in _sidecar.read_sidecar()}
        if sidecar_file.exists() and not tracked_labels:
            if _sidecar_json_is_corrupt(sidecar_file):
                logger.warning(
                    "skipping GC: sidecar %s appears corrupt",
                    sidecar_file,
                )
                return 0

        removed = 0
        uid = os.getuid()
        for plist_path in sorted(plist_dir.glob("*.plist")):
            label = plist_path.stem
            # Validate that the label looks like one of ours; ignore
            # foreign plists that may have ended up in this dir.
            try:
                parse_label(label)
            except ValueError:
                continue

            if label in tracked_labels:
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
