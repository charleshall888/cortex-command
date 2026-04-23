"""Daytime pipeline driver — single-feature async CLI.

Thin async CLI driver for daytime (foreground) execution of a single
feature via the existing overnight execution pipeline
(``execute_feature`` -> ``apply_feature_result`` -> ``cleanup_worktree``).

Provides startup-layer helpers (CWD guard, PID file I/O and liveness
check, SIGKILL recovery sequence, ``build_config`` factory) and the
async execution driver (``run_daytime``) plus CLI entry point
(``build_parser``, ``_run``).
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.overnight.auth import ensure_sdk_auth
from cortex_command.overnight.batch_runner import BatchConfig
from cortex_command.overnight.deferral import DEFAULT_DEFERRED_DIR
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight.orchestrator import BatchResult
from cortex_command.overnight.outcome_router import OutcomeContext, apply_feature_result
from cortex_command.overnight.state import (
    DaytimeResult,
    OvernightFeatureStatus,
    OvernightState,
    save_daytime_result,
    save_state,
)
from cortex_command.overnight.types import CircuitBreakerState
from cortex_command.pipeline.worktree import cleanup_worktree, create_worktree

# Compiled regex for PR URL scanning (used by _scan_pr_url).
_PR_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+")

# Compiled regex for validating DAYTIME_DISPATCH_ID format.
_DISPATCH_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def _check_cwd() -> None:
    """Abort if the CLI is not launched from the repo root.

    All path construction in ``feature_executor`` and ``outcome_router``
    is CWD-relative, so running from the wrong directory would silently
    write artifacts to the wrong locations.
    """
    if not Path("lifecycle").is_dir():
        sys.stderr.write(
            "error: must be run from the repo root "
            "(lifecycle/ directory not found)\n"
        )
        sys.exit(1)


def _pid_path(feature: str) -> Path:
    """Return the PID file path for a given feature."""
    return Path(f"lifecycle/{feature}/daytime.pid")


def _read_pid(pid_path: Path) -> Optional[int]:
    """Read a PID file and return the integer PID, or None on missing/parse error."""
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _is_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists.

    Uses the canonical ``os.kill(pid, 0)`` liveness probe:
        - Returns True on success (signal delivered; process exists).
        - Returns True on PermissionError (process exists but owned
          by a different user).
        - Returns False on OSError with errno.ESRCH (no such process).
    """
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        # Unknown errno — default to "alive" to be conservative.
        return True


def _write_pid(pid_path: Path) -> None:
    """Write the current process's PID to ``pid_path``.

    Ensures the parent directory exists (creating it recursively if needed).
    """
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _worktree_path(feature: str) -> Path:
    """Return the worktree path for a given feature.

    Matches the same-repo resolution in cortex_command.pipeline.worktree: if
    CORTEX_WORKTREE_ROOT is set, use it; otherwise default to
    .claude/worktrees/.
    """
    override_root = os.environ.get("CORTEX_WORKTREE_ROOT")
    if override_root:
        return Path(override_root) / feature
    return Path(".claude") / "worktrees" / feature


def _recover_stale(feature: str, worktree_path: Path) -> None:
    """Recover from a SIGKILLed prior daytime run.

    Ordering (matches research.md SIGKILL recovery sequence):
        1. Abort any in-progress merge in the worktree (if MERGE_HEAD exists).
        2. Remove all ``*.lock`` files under the worktree.
        3. Force-remove the worktree (``git worktree remove --force --force``).
        4. Prune the worktree list (``git worktree prune``).

    All git subprocess calls pass ``cwd=worktree_path`` rather than ``-C``
    (per project sandbox rules — see claude/rules/sandbox-behaviors.md).
    """
    del feature  # unused — worktree_path is the canonical location

    # 1. Abort any in-progress merge in the worktree.
    merge_head = worktree_path / ".git" / "MERGE_HEAD"
    if merge_head.exists():
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=worktree_path,
            check=False,
        )

    # 2. Remove all .lock files under the worktree.
    if worktree_path.exists():
        for lock in worktree_path.rglob("*.lock"):
            try:
                lock.unlink()
            except FileNotFoundError:
                pass

    # 3. Force-remove the worktree (double-force removes locked worktrees).
    subprocess.run(
        ["git", "worktree", "remove", "--force", "--force", str(worktree_path)],
        cwd=worktree_path if worktree_path.exists() else None,
        check=False,
    )

    # 4. Prune the worktree list.
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=worktree_path if worktree_path.exists() else None,
        check=False,
    )


def _read_test_command(cwd: Path) -> str:
    """Read ``test-command`` from ``lifecycle.config.md`` frontmatter.

    Returns ``"just test"`` if the file is missing, has no frontmatter
    key, or cannot be parsed.
    """
    config_path = cwd / "lifecycle.config.md"
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "just test"

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("test-command:"):
            value = stripped[len("test-command:"):].strip()
            # Strip surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if value:
                return value
    return "just test"


def build_config(feature: str, cwd: Path, session_id: str) -> BatchConfig:
    """Construct a single-feature ``BatchConfig`` and initial state file.

    Builds per-feature paths under ``lifecycle/{feature}/``, writes an
    initial ``daytime-state.json`` (minimal ``OvernightState`` for a
    single feature), and pre-creates the per-feature deferred directory.

    Args:
        feature: Feature slug (used as directory name under lifecycle/).
        cwd: Absolute path to the repo root; used as the base for all
            per-feature paths. The CLI enforces ``cwd`` is the repo root
            via ``_check_cwd()``.
        session_id: Unique identifier for this daytime session.

    Returns:
        A ``BatchConfig`` pointing at per-feature artifact paths.
    """
    test_command = _read_test_command(cwd)

    config = BatchConfig(
        batch_id=1,
        plan_path=cwd / f"lifecycle/{feature}/plan.md",
        test_command=test_command,
        base_branch="main",
        overnight_state_path=cwd / f"lifecycle/{feature}/daytime-state.json",
        overnight_events_path=cwd / f"lifecycle/{feature}/events.log",
        result_dir=cwd / f"lifecycle/{feature}",
        pipeline_events_path=cwd / f"lifecycle/{feature}/pipeline-events.log",
    )

    state = OvernightState(
        session_id=session_id,
        plan_ref=str(config.plan_path),
        current_round=1,
        phase="executing",
        features={
            feature: OvernightFeatureStatus(
                status="running",
                round_assigned=1,
            ),
        },
    )
    save_state(state, config.overnight_state_path)

    (cwd / f"lifecycle/{feature}/deferred").mkdir(parents=True, exist_ok=True)

    return config


async def _orphan_guard(feature: str, pid_path: Path) -> None:
    """Background guard that cleans up if the process is orphaned.

    Loops indefinitely, sleeping 1 second between iterations. On each
    wake, checks whether the process has been orphaned (parent PID is
    1); if orphaned, calls ``cleanup_worktree(feature)``, removes
    ``pid_path``, then calls ``os._exit(1)``.

    Uses ``os._exit`` — not ``sys.exit`` — because ``sys.exit`` inside a
    coroutine raises ``SystemExit`` only within the task; the main
    coroutine would continue unaffected.
    """
    while True:
        await asyncio.sleep(1)
        if os.getppid() == 1:
            try:
                cleanup_worktree(feature)
            finally:
                pid_path.unlink(missing_ok=True)
                os._exit(1)


def _check_dispatch_id() -> str:
    """Read and validate the DAYTIME_DISPATCH_ID environment variable.

    Returns the env value if it matches ``^[a-f0-9]{32}$``. On missing or
    malformed value, generates a fresh uuid4 hex and logs a warning to
    stderr so the caller can still produce a valid result file.
    """
    raw = os.environ.get("DAYTIME_DISPATCH_ID", "")
    if raw and _DISPATCH_ID_RE.match(raw):
        return raw
    fresh = uuid.uuid4().hex
    if not raw:
        sys.stderr.write(
            "warning: DAYTIME_DISPATCH_ID not set; "
            f"using generated dispatch_id={fresh}\n"
        )
    else:
        sys.stderr.write(
            f"warning: DAYTIME_DISPATCH_ID value {raw!r} does not match "
            f"^[a-f0-9]{{32}}$; using generated dispatch_id={fresh}\n"
        )
    return fresh


def _scan_pr_url(daytime_log_path: Path) -> Optional[str]:
    """Scan ``daytime_log_path`` line-by-line for a GitHub PR URL.

    Uses the compiled regex ``_PR_URL_RE`` and short-circuits on the first
    match. Returns the first match or ``None`` if the file is absent,
    unreadable, or contains no matching URL.
    """
    try:
        with open(daytime_log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _PR_URL_RE.search(line)
                if m:
                    return m.group(0)
    except (FileNotFoundError, OSError):
        pass
    return None


async def run_daytime(feature: str) -> int:
    """Orchestrate the full daytime lifecycle for a single feature.

    Steps: startup checks -> PID write -> worktree create -> execute ->
    route -> cleanup. Includes an orphan-prevention background task.

    Returns the process exit code (0 on merge success, 1 otherwise).
    """
    _check_cwd()

    # Capture per-dispatch identity and start time before anything can fail.
    start_ts = datetime.now(timezone.utc).isoformat()
    dispatch_id = _check_dispatch_id()

    # Result-file tracking state — updated by each code path.
    _top_exc: Optional[Exception] = None
    _terminated_via: str = "exception"
    _outcome: str = "unknown"
    _startup_phase: bool = True
    _orphan_task: Optional[asyncio.Task] = None

    # Alias for the daytime log path used by the PR-URL scanner.
    daytime_log_path = Path(f"lifecycle/{feature}/daytime.log")

    try:
        # Phase A: resolve SDK auth vector. Must run INSIDE the try-block so
        # the outer except/finally classify a no-vector hard-fail as
        # startup_failure and write daytime-result.json. Buffer the event
        # payload for Phase B emission once pipeline_events_path is known.
        auth_event = ensure_sdk_auth(event_log_path=None)
        if auth_event["vector"] == "none":
            sys.stderr.write(
                "error: no auth vector available: "
                f"{auth_event['message']}\n"
            )
            _top_exc = RuntimeError(
                "no auth vector available: " + auth_event["message"]
            )
            _terminated_via = "startup_failure"
            _outcome = "failed"
            return 1

        plan_path = Path(f"lifecycle/{feature}/plan.md")
        if not plan_path.exists():
            sys.stderr.write(
                f"error: plan.md not found at `lifecycle/{feature}/plan.md`\n"
            )
            _top_exc = FileNotFoundError(
                f"plan.md not found at lifecycle/{feature}/plan.md"
            )
            _terminated_via = "startup_failure"
            _outcome = "failed"
            return 1

        cwd = Path.cwd()
        pid_path = _pid_path(feature)

        existing_pid = _read_pid(pid_path)
        if existing_pid is not None:
            if _is_alive(existing_pid):
                msg = (
                    f"daytime already running for {feature} "
                    f"(pid {existing_pid})"
                )
                sys.stderr.write(f"error: {msg}\n")
                _top_exc = RuntimeError(msg)
                _terminated_via = "startup_failure"
                _outcome = "failed"
                return 1
            # Stale PID — recover.
            _recover_stale(feature, _worktree_path(feature))
            pid_path.unlink(missing_ok=True)

        _write_pid(pid_path)

        session_id = os.environ.get("LIFECYCLE_SESSION_ID") or (
            f"daytime-{feature}-{int(time.time())}"
        )
        config = build_config(feature, cwd, session_id)
        deferred_dir = cwd / f"lifecycle/{feature}/deferred"

        # Phase B: emit the buffered auth_bootstrap event to pipeline-events.log.
        # Byte-format matches cortex_command.pipeline.state.log_event (single
        # json.dumps(event) + "\n", parent dir pre-created). The event dict
        # already has "ts" first from ensure_sdk_auth.
        pipeline_events_path = config.pipeline_events_path
        pipeline_events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pipeline_events_path, "a", encoding="utf-8") as _auth_log:
            _auth_log.write(json.dumps(auth_event["event"]) + "\n")

        worktree_info = create_worktree(feature)

        ctx = OutcomeContext(
            batch_result=BatchResult(batch_id=1),
            lock=asyncio.Lock(),
            cb_state=CircuitBreakerState(),
            recovery_attempts_map={feature: 0},
            worktree_paths={feature: worktree_info.path},
            worktree_branches={feature: worktree_info.branch},
            repo_path_map={feature: None},
            integration_worktrees={},
            integration_branches={},
            session_id=session_id,
            backlog_ids={feature: None},
            feature_names=[feature],
            config=config,
        )

        # Flip startup phase flag before creating the orphan task — any
        # exception from here onward is "exception" not "startup_failure".
        _startup_phase = False
        _orphan_task = asyncio.create_task(_orphan_guard(feature, pid_path))  # noqa: assigned to outer scope

        try:
            result = await execute_feature(
                feature, worktree_info.path, config, deferred_dir=deferred_dir
            )
            await apply_feature_result(
                feature, result, ctx, deferred_dir=deferred_dir
            )
        except Exception as e:
            sys.stderr.write(f"error: daytime pipeline failed: {e}\n")
            _top_exc = e
            _terminated_via = "exception"
            _outcome = "failed"
            return 1
        finally:
            _orphan_task.cancel()
            cleanup_worktree(feature)
            pid_path.unlink(missing_ok=True)

        # Classification branches — all set _terminated_via / _outcome before
        # returning so the outer finally can write the correct result file.
        br = ctx.batch_result
        if feature in br.features_merged:
            _terminated_via = "classification"
            _outcome = "merged"
            print(f"Feature {feature} merged successfully.", flush=True)
            return 0
        if any(d.get("name") == feature for d in br.features_deferred):
            _terminated_via = "classification"
            _outcome = "deferred"
            deferral_file = next(deferred_dir.glob("*.md"), None)
            if deferral_file is not None:
                print(str(deferral_file), flush=True)
            else:
                print(
                    f"Feature {feature} deferred — check "
                    f"lifecycle/{feature}/deferred/ for details.",
                    flush=True,
                )
            return 1
        if any(d.get("name") == feature for d in br.features_paused):
            _terminated_via = "classification"
            _outcome = "paused"
            print(
                f"Feature {feature} paused — worktree cleaned; "
                f"check events.log for details.",
                flush=True,
            )
            return 1
        # failed or unrecognized
        _terminated_via = "classification"
        _outcome = "failed"
        failed = next(
            (d for d in br.features_failed if d.get("name") == feature),
            None,
        )
        if failed is not None and failed.get("error"):
            print(f"Feature {feature} failed: {failed['error']}", flush=True)
        else:
            print(f"Feature {feature} did not complete successfully.", flush=True)
        return 1

    except Exception as e:
        _top_exc = e
        if _startup_phase:
            _terminated_via = "startup_failure"
        else:
            _terminated_via = "exception"
        _outcome = "failed"
        sys.stderr.write(f"error: daytime pipeline failed: {e}\n")
        return 1

    finally:
        # Spec Edge Case §line 129: first statement must cancel the orphan guard
        # so it cannot fire after the outer finally begins executing.
        if _orphan_task is not None:
            _orphan_task.cancel()

        # Compute deferred file paths as absolute paths (spec R2, line 21).
        deferred_glob_dir = Path(f"lifecycle/{feature}/deferred")
        if deferred_glob_dir.is_dir():
            deferred_files = [
                str(p.resolve()) for p in sorted(deferred_glob_dir.glob("*.md"))
            ]
        else:
            deferred_files = []

        # Determine error text.
        # For exception/startup_failure paths: use the captured exception.
        # For the classification-failed path: extract from features_failed
        # (spec R2 line 76). For other classification outcomes: None.
        error_text: Optional[str]
        if _terminated_via in ("exception", "startup_failure"):
            error_text = str(_top_exc) if _top_exc is not None else None
        elif _terminated_via == "classification" and _outcome == "failed":
            # Extract error from batch_result.features_failed if available.
            try:
                br = ctx.batch_result  # type: ignore[name-defined]
                failed_entry = next(
                    (d for d in br.features_failed if d.get("name") == feature),
                    None,
                )
                error_text = (
                    failed_entry.get("error") if failed_entry is not None else None
                )
            except NameError:
                # ctx not yet defined (startup failure before ctx was created).
                error_text = None
        else:
            error_text = None

        result_obj = DaytimeResult(
            schema_version=1,
            dispatch_id=dispatch_id,
            feature=feature,
            start_ts=start_ts,
            end_ts=datetime.now(timezone.utc).isoformat(),
            outcome=_outcome,
            terminated_via=_terminated_via,
            deferred_files=deferred_files,
            error=error_text,
            pr_url=_scan_pr_url(daytime_log_path),
        )

        result_path = Path(f"lifecycle/{feature}/daytime-result.json")
        try:
            save_daytime_result(result_obj, result_path)
        except Exception as write_err:
            sys.stderr.write(
                f"warning: failed to write daytime-result.json: {write_err}\n"
            )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="python3 -m cortex_command.overnight.daytime_pipeline"
    )
    p.add_argument(
        "--feature",
        required=True,
        help="Feature slug to execute (e.g. my-feature)",
    )
    return p


def _run() -> None:
    args = build_parser().parse_args()
    sys.exit(asyncio.run(run_daytime(args.feature)))


if __name__ == "__main__":
    _run()
