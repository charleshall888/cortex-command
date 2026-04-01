"""Integration branch test-failure recovery for overnight orchestration.

When the integration branch tests fail after merging a feature, this module
performs a flaky guard re-run and, on confirmed failure, dispatches a repair
agent to fix the code.

Follows the CLI module pattern established by interrupt.py and the flaky
guard + SHA circuit breaker pattern from claude/pipeline/merge_recovery.py.

Callable as:
    python3 -m claude.overnight.integration_recovery [--state ...] [--test-command ...] ...
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from claude.overnight.events import (
    INTEGRATION_RECOVERY_FAILED,
    INTEGRATION_RECOVERY_START,
    INTEGRATION_RECOVERY_SUCCESS,
    log_event,
)
from claude.overnight.state import load_state

try:
    from claude.pipeline.dispatch import dispatch_task
    _DISPATCH_AVAILABLE = True
except ImportError:
    _DISPATCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Repair prompt template
# ---------------------------------------------------------------------------

INTEGRATION_REPAIR_PROMPT_TEMPLATE = """\
## Integration Branch Test-Failure Recovery

The integration branch tests are failing. Your job is to fix the code so that
the tests pass.

### Initial failing test output
```
{test_output}
```

### Diff (main..HEAD)
```
{diff}
```

### Hard constraints
- Fix the implementation code to make the existing tests pass.
- Do not modify test files unless the test was introduced by the feature's own
  commits and you write an explicit deferral with reason in your exit report
  explaining why the test itself needs changing rather than the implementation.
- Commit all changes before finishing.
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log(event: str, round_num: int, events_path: str, details: dict) -> None:
    """Log an event, no-op if events_path is empty."""
    if not events_path:
        return
    log_event(
        event,
        round=round_num,
        feature=None,
        details=details,
        log_path=Path(events_path),
    )


def _get_head_sha(worktree_path: str) -> str:
    """Return HEAD SHA in worktree_path, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=15,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _get_diff(worktree_path: str) -> str:
    """Return git diff main..HEAD truncated to 4000 chars."""
    try:
        result = subprocess.run(
            ["git", "diff", "main..HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=30,
        )
        output = result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        output = ""
    return output[:4000]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point for python3 -m claude.overnight.integration_recovery."""
    parser = argparse.ArgumentParser(
        description="Integration branch test-failure recovery for overnight orchestration.",
    )
    parser.add_argument("--state", dest="state", default="", metavar="STATE_PATH")
    parser.add_argument("--test-command", dest="test_command", default="", metavar="CMD")
    parser.add_argument("--worktree", dest="worktree", default="", metavar="WORKTREE_PATH")
    parser.add_argument("--events-path", dest="events_path", default="", metavar="EVENTS_PATH")
    parser.add_argument("--test-output", dest="test_output", default="", metavar="SNIPPET")
    args = parser.parse_args()

    worktree_path = args.worktree
    test_command = args.test_command
    events_path = args.events_path
    test_output_snippet = args.test_output

    # Guard: worktree must exist
    if not worktree_path or not Path(worktree_path).is_dir():
        print(
            f"integration_recovery: error: worktree path {worktree_path!r} "
            "does not exist or was not provided",
            file=sys.stderr,
        )
        return 1

    # Read round number from state
    round_num = 0
    if args.state:
        try:
            state = load_state(Path(args.state))
            round_num = state.current_round
        except Exception:
            round_num = 0

    # Log start
    _log(
        INTEGRATION_RECOVERY_START,
        round_num,
        events_path,
        {"worktree": worktree_path},
    )

    # --- Flaky guard ---
    try:
        flaky_result = subprocess.run(
            ["bash", "-c", test_command],
            capture_output=True,
            cwd=worktree_path,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"integration_recovery: flaky guard failed: {exc}", file=sys.stderr)
        _log(
            INTEGRATION_RECOVERY_FAILED,
            round_num,
            events_path,
            {"reason": "flaky_guard_error"},
        )
        return 1

    if flaky_result.returncode == 0:
        _log(
            INTEGRATION_RECOVERY_SUCCESS,
            round_num,
            events_path,
            {"flaky": True},
        )
        return 0

    # --- SHA before repair ---
    sha_before = _get_head_sha(worktree_path)

    # --- Truncated diff ---
    diff = _get_diff(worktree_path)

    # --- Build repair prompt ---
    prompt = INTEGRATION_REPAIR_PROMPT_TEMPLATE.format(
        test_output=test_output_snippet,
        diff=diff,
    )

    # --- Dispatch repair agent ---
    if not _DISPATCH_AVAILABLE:
        print(
            "integration_recovery: warning: claude.pipeline.dispatch is not available "
            "(SDK not installed); cannot dispatch repair agent",
            file=sys.stderr,
        )
        _log(
            INTEGRATION_RECOVERY_FAILED,
            round_num,
            events_path,
            {"reason": "dispatch_unavailable"},
        )
        return 1

    asyncio.run(
        dispatch_task(
            feature="integration-recovery",
            task=prompt,
            worktree_path=Path(worktree_path),
            complexity="complex",
            system_prompt=prompt,
            log_path=Path(events_path) if events_path else None,
        )
    )

    # --- SHA circuit breaker ---
    sha_after = _get_head_sha(worktree_path)
    if sha_before == sha_after:
        _log(
            INTEGRATION_RECOVERY_FAILED,
            round_num,
            events_path,
            {"reason": "no_commits"},
        )
        return 1

    # --- Re-test ---
    try:
        retest_result = subprocess.run(
            ["bash", "-c", test_command],
            capture_output=True,
            cwd=worktree_path,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"integration_recovery: re-test failed: {exc}", file=sys.stderr)
        _log(
            INTEGRATION_RECOVERY_FAILED,
            round_num,
            events_path,
            {"reason": "retest_error"},
        )
        return 1

    if retest_result.returncode == 0:
        _log(
            INTEGRATION_RECOVERY_SUCCESS,
            round_num,
            events_path,
            {},
        )
        return 0

    _log(
        INTEGRATION_RECOVERY_FAILED,
        round_num,
        events_path,
        {"reason": "tests_still_failing"},
    )
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
