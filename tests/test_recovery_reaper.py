"""Tests for the env-match orphan reaper (spec §R5, Phase 1).

:func:`cortex_command.overnight.recovery.reap_session_orphans` enumerates
processes via ``psutil`` and selects only those whose environment carries
BOTH ``CORTEX_RUNNER_CHILD == "1"`` AND ``LIFECYCLE_SESSION_ID ==
session_id`` (the identity anchor), then SIGTERM → grace → SIGKILL per
matched process, as a bounded fixpoint loop. These tests drive selection
through a monkeypatched ``psutil.process_iter`` (and ``psutil.wait_procs``)
returning fake process objects with controlled ``environ()`` /
``create_time()`` — no real process is signalled. They assert the spec's
discriminating cases:

  (a) only env-matched (BOTH markers) pids are selected;
  (b) a ``claude`` process carrying a matching ``LIFECYCLE_SESSION_ID`` but
      lacking ``CORTEX_RUNNER_CHILD`` is never selected (the interactive-
      session safety case);
  (c) a matched child that appears only on the second enumeration pass is
      reaped by the fixpoint loop.

Per-process robustness (un-introspectable env → non-match, vanished pid →
skip) is also covered.
"""

from __future__ import annotations

import psutil

from cortex_command.overnight import recovery
from cortex_command.overnight.recovery import ReapOutcome, reap_session_orphans

SESSION_ID = "2026-04-24-12-00-00"


class FakeProc:
    """A fake ``psutil.Process`` with controlled env / create_time / signals.

    Mimics the surface the reaper touches: ``pid``, ``environ()``,
    ``create_time()``, ``terminate()``, ``kill()``. ``terminate`` records the
    call and (unless ``survive_grace`` is set) marks the proc as exited so a
    subsequent ``create_time()``/``kill()`` reflects a vanished process. The
    reaper accesses ``proc.info`` only when ``process_iter`` populates it; this
    fake deliberately has no ``info`` attribute, so the reaper falls back to
    the ``environ()`` / ``create_time()`` method path (the path tests drive).
    """

    def __init__(
        self,
        pid: int,
        environ: dict | None,
        *,
        create_time: float = 1000.0,
        survive_grace: bool = False,
        environ_raises: type[BaseException] | None = None,
    ) -> None:
        self.pid = pid
        self._environ = environ
        self._create_time = create_time
        self._survive_grace = survive_grace
        self._environ_raises = environ_raises
        self.terminated = False
        self.killed = False
        self._alive = True

    def environ(self) -> dict:
        if self._environ_raises is not None:
            raise self._environ_raises(self.pid, "fake")
        if self._environ is None:
            raise psutil.AccessDenied(self.pid, "fake")
        return self._environ

    def create_time(self) -> float:
        if not self._alive:
            raise psutil.NoSuchProcess(self.pid)
        return self._create_time

    def terminate(self) -> None:
        if not self._alive:
            raise psutil.NoSuchProcess(self.pid)
        self.terminated = True
        if not self._survive_grace:
            self._alive = False

    def kill(self) -> None:
        if not self._alive:
            raise psutil.NoSuchProcess(self.pid)
        self.killed = True
        self._alive = False


def _matched_env(session_id: str = SESSION_ID) -> dict:
    """Env for a runner-spawned orphan (both markers present)."""
    return {"CORTEX_RUNNER_CHILD": "1", "LIFECYCLE_SESSION_ID": session_id}


def _interactive_env(session_id: str = SESSION_ID) -> dict:
    """Env for an operator's interactive ``claude`` session.

    Carries ``LIFECYCLE_SESSION_ID`` (exported by the SessionStart hook in a
    cortex repo) but NOT ``CORTEX_RUNNER_CHILD`` — must never be selected.
    """
    return {"LIFECYCLE_SESSION_ID": session_id}


def _patch_iter(monkeypatch, passes: list[list[FakeProc]]) -> None:
    """Monkeypatch ``psutil.process_iter`` to yield successive ``passes``.

    Each call to ``process_iter`` returns the next list from ``passes`` (the
    last list repeats once exhausted, modelling a stable population). Also
    stubs ``psutil.wait_procs`` to a deterministic grace result derived from
    each fake's ``_alive`` flag so no real wait/signal occurs.
    """
    calls = {"n": 0}

    def fake_iter(attrs=None):
        idx = min(calls["n"], len(passes) - 1)
        calls["n"] += 1
        return list(passes[idx])

    def fake_wait_procs(procs, timeout=None):
        gone = [p for p in procs if not getattr(p, "_alive", False)]
        alive = [p for p in procs if getattr(p, "_alive", False)]
        return gone, alive

    monkeypatch.setattr(recovery.psutil, "process_iter", fake_iter)
    monkeypatch.setattr(recovery.psutil, "wait_procs", fake_wait_procs)


def test_only_env_matched_pids_selected(monkeypatch) -> None:
    """(a) Only pids with BOTH markers are selected and signalled.

    A matched orphan, a same-session interactive ``claude`` (no
    ``CORTEX_RUNNER_CHILD``), an other-session orphan, and an
    un-introspectable process coexist; only the matched orphan is reaped.
    """
    matched = FakeProc(101, _matched_env())
    interactive = FakeProc(102, _interactive_env())
    other_session = FakeProc(103, _matched_env("9999-99-99-99-99-99"))
    no_env = FakeProc(104, None)  # AccessDenied -> non-match

    _patch_iter(monkeypatch, [[matched, interactive, other_session, no_env], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    assert isinstance(outcome, ReapOutcome)
    assert outcome.matched == [101]
    assert matched.terminated is True
    # Non-matches are never signalled.
    assert interactive.terminated is False and interactive.killed is False
    assert other_session.terminated is False and other_session.killed is False
    assert no_env.terminated is False and no_env.killed is False


def test_interactive_session_never_selected(monkeypatch) -> None:
    """(b) A same-session ``claude`` lacking CORTEX_RUNNER_CHILD is safe.

    The interactive-session safety case: ``LIFECYCLE_SESSION_ID`` alone must
    NOT select a process — collapsing the AND would kill operator sessions.
    """
    interactive = FakeProc(201, _interactive_env())

    _patch_iter(monkeypatch, [[interactive], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    assert outcome.matched == []
    assert outcome.terminated == [] and outcome.killed == []
    assert interactive.terminated is False and interactive.killed is False


def test_fixpoint_reaps_second_pass_child(monkeypatch) -> None:
    """(c) A child appearing only on the 2nd enumeration is still reaped.

    Models a matched worker forking a fresh child during the grace window:
    pass 1 sees only the parent; pass 2 sees the late child; pass 3 is clean.
    The fixpoint loop must reap both.
    """
    parent = FakeProc(301, _matched_env())
    late_child = FakeProc(302, _matched_env())

    _patch_iter(monkeypatch, [[parent], [late_child], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    assert set(outcome.matched) == {301, 302}
    assert parent.terminated is True
    assert late_child.terminated is True
    assert outcome.unreaped == []


def test_survivor_is_sigkilled_after_grace(monkeypatch) -> None:
    """A matched proc surviving the grace window is SIGKILLed."""
    survivor = FakeProc(401, _matched_env(), survive_grace=True)

    # After the kill the proc is dead, so the next enumeration pass is clean.
    _patch_iter(monkeypatch, [[survivor], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    assert survivor.terminated is True
    assert survivor.killed is True
    assert 401 in outcome.killed
    assert 401 not in outcome.terminated


def test_unreaped_surfaced_at_fixpoint_cap(monkeypatch) -> None:
    """A proc that keeps matching at the cap is surfaced as un-reaped.

    Models a marker-carrying class the reaper cannot bring down (it survives
    every grace window). It must be surfaced in ``unreaped`` — never broad-
    matched into a ``claude`` kill.
    """
    stubborn = FakeProc(501, _matched_env(), survive_grace=True)

    # SIGKILL is a no-op for this fake (override kill to not flip _alive), so
    # it keeps matching on every pass.
    def noop_kill() -> None:
        stubborn.killed = True

    stubborn.kill = noop_kill  # type: ignore[method-assign]

    # The population is stable across all passes (never goes empty).
    _patch_iter(monkeypatch, [[stubborn]])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0, max_passes=3)

    assert 501 in outcome.matched
    assert 501 in outcome.unreaped


def test_toctou_create_time_change_skips_kill(monkeypatch) -> None:
    """A pid whose create_time changed between enumeration and kill is skipped.

    The reaper re-reads ``create_time`` via ``proc.info`` (enumeration-time)
    vs a live ``create_time()``; a mismatch means pid reuse and the proc is
    skipped. Here the fake reports its enumeration baseline via an ``info``
    dict that diverges from the live read.
    """

    class InfoProc(FakeProc):
        def __init__(self, pid, environ, enum_ct, live_ct):
            super().__init__(pid, environ, create_time=live_ct)
            # process_iter would populate proc.info; emulate it.
            self.info = {"environ": environ, "create_time": enum_ct}

    reused = InfoProc(601, _matched_env(), enum_ct=1000.0, live_ct=2000.0)

    _patch_iter(monkeypatch, [[reused], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    # It is env-matched (selected) but the TOCTOU guard skips the signal.
    assert 601 in outcome.matched
    assert reused.terminated is False and reused.killed is False


def test_per_process_exception_does_not_block_rest(monkeypatch) -> None:
    """One proc whose environ() raises does not block reaping the rest."""
    boom = FakeProc(701, None, environ_raises=psutil.AccessDenied)
    good = FakeProc(702, _matched_env())

    _patch_iter(monkeypatch, [[boom, good], []])

    outcome = reap_session_orphans(SESSION_ID, graceful_timeout=0.0)

    assert outcome.matched == [702]
    assert good.terminated is True
    assert boom.terminated is False
