"""Tests for daytime pre-flight guards (§1b Daytime Dispatch).

Covers the guard logic added to `skills/lifecycle/references/implement.md` §1b:
a `daytime.pid` double-dispatch guard, a concurrent overnight runner guard,
polling-loop startup-failure fallback, first-match-wins outcome detection, and
the document contract for the §1b section.

The guard logic is exercised as Python helper functions that mirror the Bash
sequence described in §1b so that behavior can be unit-tested deterministically
without launching the real skill. The real §1b implementation reads the global
`~/.local/share/overnight-sessions/active-session.json` pointer; the
`_check_overnight_guard` helper accepts the session file path as a parameter
so tests can pass a `tmp_path`-owned version.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Guard helpers (mirror the §1b Bash sequence as testable Python)
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    """Equivalent to `kill -0 $pid 2>/dev/null`."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        # PermissionError means the process exists but is owned by another
        # user — from the guard's perspective, still "alive".
        if isinstance(sys.exc_info()[1], PermissionError):
            return True
        return False
    except OSError:
        return False
    return True


def _check_daytime_pid_guard(pid_file: Path) -> tuple[bool, str]:
    """Daytime-PID double-dispatch guard.

    Returns (reject, message). reject=True means the guard fired and the
    skill must abort with `message`; reject=False means "proceed".
    """
    if not pid_file.exists():
        return False, "proceed"
    content = pid_file.read_text().strip()
    if not content:
        return False, "proceed"
    try:
        pid = int(content)
    except ValueError:
        return False, "proceed"
    if _pid_alive(pid):
        return True, (
            f"Autonomous daytime run already in progress (PID {pid}) — "
            "wait for it to complete or check events.log"
        )
    return False, "proceed"


def _check_overnight_guard(session_file: Path, cwd: Path) -> tuple[bool, str]:
    """Concurrent-overnight guard.

    Mirrors the four-step sequence from §1b: read active-session.json, match
    repo_path + phase==executing, derive session_dir from Path(state_path).parent,
    read .runner.lock, liveness-check runner PID.

    The real §1b implementation reads `~/.local/share/overnight-sessions/
    active-session.json`; tests pass a tmp_path session file instead.
    """
    if not session_file.exists():
        return False, "proceed"
    raw = session_file.read_text().strip()
    if not raw:
        return False, "proceed"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False, "proceed"

    repo_path = data.get("repo_path")
    phase = data.get("phase")
    state_path = data.get("state_path")
    if repo_path != str(cwd) or phase != "executing" or not state_path:
        return False, "proceed"

    session_dir = Path(state_path).parent
    lock_file = session_dir / ".runner.lock"
    if not lock_file.exists():
        return False, "proceed"
    lock_content = lock_file.read_text().strip()
    if not lock_content:
        return False, "proceed"
    try:
        runner_pid = int(lock_content)
    except ValueError:
        return False, "proceed"

    if _pid_alive(runner_pid):
        return True, (
            f"Overnight runner is active (PID {runner_pid}) — "
            "wait for it to complete before launching a daytime run."
        )
    return False, "proceed"


def _polling_fallback_path(pid_file: Path, daytime_log: Path) -> str:
    """Simulate the polling initial-wait decision from §1b.vi.

    After the initial ~10s wait, if daytime.pid is absent the skill skips the
    polling loop and goes directly to result surfacing using daytime.log.
    Returns "read_log" for the fallback path, or "poll" for the normal path.
    """
    if not pid_file.exists():
        # Fallback: surface results by reading daytime.log content directly.
        _ = daytime_log.read_text() if daytime_log.exists() else ""
        return "read_log"
    return "poll"


def _detect_outcome(daytime_log: Path) -> str:
    """First-match-wins outcome detection from §1b.vii.

    Reads the last non-empty "Feature " line and classifies in this exact
    order: merged successfully → complete, deferred → deferred, paused →
    paused, otherwise failed.
    """
    if not daytime_log.exists():
        return "failed"
    last_feature_line = ""
    for raw_line in daytime_log.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Feature "):
            last_feature_line = line
    if not last_feature_line:
        return "failed"
    if "merged successfully" in last_feature_line:
        return "complete"
    if "deferred" in last_feature_line:
        return "deferred"
    # "failed" is checked ahead of "paused" so that a failure message that
    # happens to contain "paused" as an incidental substring (e.g.
    # `"Feature X failed: subprocess paused unexpectedly"`) classifies as
    # failed. This mirrors the intent documented in §1b.vii: ordered
    # detection must not let substring accidents misclassify the outcome.
    if "failed" in last_feature_line:
        return "failed"
    if "paused" in last_feature_line:
        return "paused"
    return "failed"


def _dead_pid() -> int:
    """Spawn a trivial subprocess, wait for it to exit, return its PID.

    The PID is guaranteed to be dead at the moment we return it. A kernel
    could reassign the PID eventually, but within the narrow test window
    that's a non-issue in practice for this test suite.
    """
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


# ---------------------------------------------------------------------------
# Guard tests (Req 12)
# ---------------------------------------------------------------------------


def test_double_dispatch_guard_live_pid(tmp_path: Path) -> None:
    """daytime.pid containing the current (live) PID must reject dispatch."""
    pid_file = tmp_path / "daytime.pid"
    pid_file.write_text(f"{os.getpid()}\n")

    reject, message = _check_daytime_pid_guard(pid_file)

    assert reject is True
    assert "already in progress" in message


def test_overnight_guard_live_runner(tmp_path: Path) -> None:
    """Live runner for this repo must reject with the documented message."""
    tmp_session_dir = tmp_path / "sessions" / "abc123"
    tmp_session_dir.mkdir(parents=True)

    state_path = tmp_session_dir / "overnight-state.json"
    state_path.write_text("{}")

    # Independently validate the .parent derivation step §1b relies on
    # before we exercise the guard helper.
    assert Path(str(state_path)).parent == tmp_session_dir

    (tmp_session_dir / ".runner.lock").write_text(f"{os.getpid()}\n")

    session_file = tmp_path / "active-session.json"
    session_file.write_text(
        json.dumps(
            {
                "repo_path": str(tmp_path),
                "phase": "executing",
                "state_path": str(state_path),
            }
        )
    )

    reject, message = _check_overnight_guard(session_file, cwd=tmp_path)

    assert reject is True
    assert "Overnight runner is active" in message


def test_double_dispatch_guard_stale_pid(tmp_path: Path) -> None:
    """daytime.pid with a dead PID must NOT fire the guard."""
    dead_pid = _dead_pid()
    # Sanity: the PID should read as dead right now.
    assert _pid_alive(dead_pid) is False, (
        f"PID {dead_pid} unexpectedly still alive — test precondition failed"
    )

    pid_file = tmp_path / "daytime.pid"
    pid_file.write_text(f"{dead_pid}\n")

    reject, message = _check_daytime_pid_guard(pid_file)

    assert reject is False
    assert message == "proceed"


def test_overnight_guard_different_repo(tmp_path: Path) -> None:
    """repo_path mismatch must skip the guard even with a live runner."""
    tmp_session_dir = tmp_path / "sessions" / "abc123"
    tmp_session_dir.mkdir(parents=True)
    state_path = tmp_session_dir / "overnight-state.json"
    state_path.write_text("{}")
    (tmp_session_dir / ".runner.lock").write_text(f"{os.getpid()}\n")

    session_file = tmp_path / "active-session.json"
    session_file.write_text(
        json.dumps(
            {
                "repo_path": "/some/other/repo",
                "phase": "executing",
                "state_path": str(state_path),
            }
        )
    )

    reject, message = _check_overnight_guard(session_file, cwd=tmp_path)

    assert reject is False
    assert message == "proceed"


def test_overnight_guard_no_session_file(tmp_path: Path) -> None:
    """Absent active-session.json must skip the guard."""
    session_file = tmp_path / "active-session.json"
    assert not session_file.exists()

    reject, message = _check_overnight_guard(session_file, cwd=tmp_path)

    assert reject is False
    assert message == "proceed"


def test_polling_fallback_startup_failure(tmp_path: Path) -> None:
    """No daytime.pid after initial wait → fallback reads daytime.log."""
    pid_file = tmp_path / "daytime.pid"
    daytime_log = tmp_path / "daytime.log"
    daytime_log.write_text(
        "starting...\nFeature widget failed: crashed during startup\n"
    )

    # pid_file absent simulates the subprocess crashing before it could
    # write its PID.
    assert not pid_file.exists()

    path = _polling_fallback_path(pid_file, daytime_log)

    assert path == "read_log"


def test_outcome_detection_paused_substring_in_failure(tmp_path: Path) -> None:
    """'paused' as a substring in a failure message must classify as failed."""
    daytime_log = tmp_path / "daytime.log"
    daytime_log.write_text(
        "Starting pipeline...\n"
        "Feature X queued\n"
        "Feature X failed: subprocess paused unexpectedly\n"
    )

    outcome = _detect_outcome(daytime_log)

    assert outcome == "failed"
    assert outcome != "paused"


# ---------------------------------------------------------------------------
# Contract test (Req 13)
# ---------------------------------------------------------------------------


def test_skill_contracts() -> None:
    """implement.md §1a (Interactive Worktree Creation) must satisfy invariants.

    The legacy daytime-pipeline contract was removed by lifecycle
    `manage-interactive-feature-worktree-lifecycle-creation` T10 — option 2
    now creates an `interactive/{slug}` worktree and hands off to the user
    (Variant A `cd` / Variant B fresh session, owned by epic #240).

    Checks:
      (a) `create_worktree(feature="interactive-` invocation appears in §iii
      (b) `interactive/{slug}` branch shape is documented
      (c) Interactive PID liveness check (§i) precedes overnight guard (§ii)
          which precedes worktree creation (§iii)
      (d) The two pre-flight rejections are documented (interactive PID live,
          overnight runner active for this repo)
      (e) Handoff message documents both Variant A (cd) and Variant B
          (`claude --worktree=`)
      (f) §v explicitly exits /cortex-core:lifecycle without transitioning
    """
    implement_md = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"
    text = implement_md.read_text()

    match = re.search(r"### 1a\..*?(?=\n### )", text, flags=re.DOTALL)
    assert match is not None, "could not locate §1a section in implement.md"
    full_section = match.group(0)

    steps_start = full_section.find("**i.")
    assert steps_start != -1, "§1a must contain a first step marker '**i.'"
    section = full_section[steps_start:]

    # (a) create_worktree invocation with interactive- prefix present
    assert 'create_worktree(feature="interactive-' in section, (
        '§1a must invoke create_worktree with the interactive- feature prefix'
    )

    # (b) branch shape documented
    assert "interactive/{slug}" in section or "interactive/" in section, (
        "§1a must document the interactive/{slug} branch shape"
    )

    # (c) ordering: interactive PID guard (§i) → overnight guard (§ii) → creation (§iii)
    i_idx = section.find("**i.")
    ii_idx = section.find("**ii.")
    iii_idx = section.find("**iii.")
    assert -1 not in (i_idx, ii_idx, iii_idx), "§1a must have steps i, ii, iii"
    assert i_idx < ii_idx < iii_idx, (
        "§1a step ordering must be i (interactive PID) → ii (overnight) → iii (create)"
    )

    # (d) pre-flight rejections documented
    assert "interactive.pid" in section, "§1a.i must reference interactive.pid"
    assert "kill -0" in section, "§1a.i must reference kill -0 liveness check"
    assert "active-session.json" in section, (
        "§1a.ii must reference active-session.json overnight guard"
    )
    assert "Overnight runner is active" in section, (
        "§1a.ii must document the overnight-active rejection message"
    )

    # (e) handoff documents Variant A and Variant B
    assert "Variant A" in section and "Variant B" in section, (
        "§1a.iv handoff must document both Variant A and Variant B"
    )
    assert "claude --worktree=" in section, (
        "§1a.iv handoff must reference `claude --worktree=` for Variant B"
    )

    # (f) §v explicit exit
    v_idx = section.find("**v.")
    assert v_idx != -1, "§1a must contain a §v exit step"
    v_tail = section[v_idx:]
    assert "Exit /cortex-core:lifecycle" in v_tail or "exit" in v_tail.lower(), (
        "§1a.v must explicitly exit the lifecycle"
    )

    # Legacy daytime-pipeline artifacts must NOT reappear (regression guard)
    for legacy in ("cortex-daytime-pipeline", "cortex-daytime-dispatch-writer",
                   "cortex-daytime-result-reader", '"mode": "daytime"'):
        assert legacy not in section, (
            f"§1a must not re-introduce removed daytime-pipeline artifact {legacy!r}"
        )


def test_plan_md_dispatcher_contracts() -> None:
    """plan.md §1b.f must keep the SEC-1 mitigation in its routing-branch context.

    The SEC-1 rationale-hiding rule is operational, not lexical — the dispatcher
    must hide the synthesizer's preliminary rationale specifically on the
    low-confidence + malformed-envelope routing branch where untrusted variant
    content could otherwise steer the operator. A grep-only check (already run
    by the spec's acceptance criterion) cannot distinguish a surviving mitigation
    from an orphan sentence whose surrounding conditional was deleted.

    This test pins the structural placement of the SEC-1 sentence in three ways:
      (a) sentence appears in §1b.f (between the `**f. Route on verdict + confidence**`
          header and the next `**g.` header)
      (b) sentence offset within §1b.f is within 400 chars of the `confidence: "low"`
          routing-branch text — pins association with the conditional
      (c) sentence offset within §1b.f is within 400 chars of the `comparison table`
          text — pins association with the dispatcher-side render context that
          gives the rule its operational meaning
    """
    plan_md = REPO_ROOT / "skills" / "lifecycle" / "references" / "plan.md"
    text = plan_md.read_text()

    # Locate §1b.f region: between `**f. Route on verdict + confidence**` and
    # the next `**g.` subsection header.
    f_anchor = re.search(r"\*\*f\. Route on verdict \+ confidence\*\*", text)
    assert f_anchor is not None, (
        "could not locate §1b.f section header in plan.md"
    )
    g_anchor = re.search(r"\*\*g\. ", text[f_anchor.start():])
    assert g_anchor is not None, (
        "could not locate §1b.g section header after §1b.f in plan.md"
    )
    section_1b_f = text[f_anchor.start() : f_anchor.start() + g_anchor.start()]

    # (a) SEC-1 sentence is present within §1b.f.
    sec1_match = re.search(
        r"preliminary rationale is hidden from the comparison table",
        section_1b_f,
    )
    assert sec1_match is not None, (
        "§1b.f must contain the SEC-1 rationale-hiding sentence "
        "(verbatim: 'preliminary rationale is hidden from the comparison table')"
    )
    sec1_offset = sec1_match.start()

    # (b) SEC-1 sentence is co-located with the low-confidence routing branch
    # (within ±400 chars). The branch governs when the rule applies.
    low_conf_match = re.search(r'confidence: "low"', section_1b_f)
    assert low_conf_match is not None, (
        '§1b.f must reference the `confidence: "low"` routing branch — '
        "this is the conditional under which SEC-1 fires"
    )
    low_conf_distance = abs(sec1_offset - low_conf_match.start())
    assert low_conf_distance <= 400, (
        f"SEC-1 sentence is {low_conf_distance} chars from the "
        f'`confidence: "low"` routing branch in §1b.f; expected ≤400. '
        "A pathological edit may have moved the sentence away from its "
        "guarding conditional, leaving the mitigation orphaned."
    )

    # (c) SEC-1 sentence is co-located with the comparison-table render
    # (within ±400 chars). The render context gives the rule operational meaning.
    table_match = re.search(r"comparison table", section_1b_f)
    assert table_match is not None, (
        "§1b.f must reference the comparison table — "
        "the dispatcher-side render context for SEC-1"
    )
    table_distance = abs(sec1_offset - table_match.start())
    assert table_distance <= 400, (
        f"SEC-1 sentence is {table_distance} chars from the "
        "`comparison table` reference in §1b.f; expected ≤400. "
        "A pathological edit may have decoupled the rationale-hiding rule "
        "from the render path it governs."
    )
