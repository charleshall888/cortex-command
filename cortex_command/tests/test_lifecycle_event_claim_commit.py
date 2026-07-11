"""Tests for the claim/commit locking primitive (374 R3, Task 6).

The primitive (:func:`cortex_command.lifecycle_event.claim_transition` /
:func:`commit_transition`) is the load-bearing correctness core of the served
advance loop: it holds the events.log sibling-lockfile flock across
read+validate+append, closing the append-only hole in ``_append_event_atomic``
(adversarial finding 1) where two deciders could both read the same pre-state
and both append conflicting transitions.

Coverage:

* Happy path — claim then commit writes exactly one ``advance_started`` and one
  ``advance_committed`` linked by ``invocation_id``.
* from_state gate — a claim whose expected from_state does not match the
  detected phase is refused.
* Claim idempotency — a second claim under the same ``invocation_id`` resumes
  the orphaned claim without a duplicate row (crash-recovery retry).
* Commit idempotency — a second commit under the same id no-ops.
* Commit without a claim is refused.
* **Interleave (mandatory)** — a typed-subcommand (``phase-transition``) row
  injected between claim and commit makes commit refuse with "state moved since
  claim" and NAME the interleaved row.
* **Race (mandatory)** — two real processes racing the same transition through
  the primitive yield exactly one ``advance_committed`` and one explicit
  refusal ("in-flight transition").

The resolver is pinned per test via ``CORTEX_REPO_ROOT`` (honoured first by the
machine-verb resolver ``resolve_events_log``), so every claim/commit and the
injected typed subcommand converge on one physical events.log / flock domain.
"""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from cortex_command.lifecycle_event import (
    ClaimResult,
    CommitResult,
    claim_transition,
    commit_transition,
    derive_invocation_id,
)
from cortex_command.lifecycle.log_resolver import resolve_events_log

FEATURE = "374-claim-commit-fixture"
# With no artifacts present, detect_lifecycle_phase() returns "research" — the
# cheapest from_state to gate against (an empty feature dir suffices).
FROM_STATE = "research"
TO_STATE = "specify"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pin_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin the machine-verb resolver to *root* and return the resolved log path.

    ``CORTEX_REPO_ROOT`` is honoured first by ``_resolve_main_repo_root`` (the
    resolver behind ``resolve_events_log``), so the whole test converges on
    ``root/cortex/lifecycle/{FEATURE}/events.log``. CWD is also moved to *root*
    so a typed subcommand (which uses the CWD resolver) lands on the same log.
    """
    (root / "cortex" / "lifecycle" / FEATURE).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.chdir(root)
    return resolve_events_log(FEATURE)


def _read_rows(log_path: Path) -> list[dict]:
    """Parse every JSONL row from *log_path* (empty list if absent)."""
    if not log_path.exists():
        return []
    rows: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _events(rows: list[dict], name: str) -> list[dict]:
    return [r for r in rows if r.get("event") == name]


# ---------------------------------------------------------------------------
# derive_invocation_id
# ---------------------------------------------------------------------------


class TestDeriveInvocationId:
    def test_deterministic_across_calls(self) -> None:
        a = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        b = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        assert a == b and a  # stable and non-empty

    def test_discriminator_distinguishes(self) -> None:
        base = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        other = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE, "session-2")
        assert base != other


# ---------------------------------------------------------------------------
# Happy path + gate + idempotency (single process)
# ---------------------------------------------------------------------------


class TestClaimCommitHappyPath:
    def test_claim_then_commit_writes_linked_pair(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)

        claim = claim_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert isinstance(claim, ClaimResult)
        assert claim.ok and claim.status == "claimed"
        assert claim.log_path == log_path

        commit = commit_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert isinstance(commit, CommitResult)
        assert commit.ok and commit.status == "committed"

        rows = _read_rows(log_path)
        started = _events(rows, "advance_started")
        committed = _events(rows, "advance_committed")
        assert len(started) == 1 and len(committed) == 1
        # Both rows carry the same invocation_id linking the pair.
        assert started[0]["invocation_id"] == inv
        assert committed[0]["invocation_id"] == inv
        # Canonical field contract.
        for row in (started[0], committed[0]):
            assert row["feature"] == FEATURE
            assert row["from_state"] == FROM_STATE
            assert row["to_state"] == TO_STATE
            assert "ts" in row

    def test_extra_fields_are_additive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE, "extra")
        claim_transition(
            FEATURE, FROM_STATE, TO_STATE, inv, extra_fields={"note": "hi"}
        )
        commit_transition(
            FEATURE, FROM_STATE, TO_STATE, inv, extra_fields={"note": "bye"}
        )
        rows = _read_rows(log_path)
        assert _events(rows, "advance_started")[0]["note"] == "hi"
        assert _events(rows, "advance_committed")[0]["note"] == "bye"


class TestFromStateGate:
    def test_claim_refused_when_phase_mismatches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, "plan", "review")
        # Detected phase is "research" (no artifacts); expected "plan" mismatches.
        claim = claim_transition(FEATURE, "plan", "review", inv)
        assert not claim.ok and claim.status == "gate-mismatch"
        assert "from_state gate" in (claim.reason or "")
        # Nothing was written.
        assert _events(_read_rows(log_path), "advance_started") == []


class TestClaimIdempotency:
    def test_same_invocation_resumes_without_duplicate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        first = claim_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert first.status == "claimed"
        second = claim_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert second.ok and second.status == "resumed"
        # Exactly one advance_started despite two claim calls (crash-retry).
        assert len(_events(_read_rows(log_path), "advance_started")) == 1


class TestCommitIdempotency:
    def test_second_commit_is_already_committed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        claim_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        first = commit_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert first.status == "committed"
        second = commit_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert second.ok and second.status == "already-committed"
        assert len(_events(_read_rows(log_path), "advance_committed")) == 1

    def test_commit_without_claim_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)
        commit = commit_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert not commit.ok and commit.status == "no-claim"
        assert _events(_read_rows(log_path), "advance_committed") == []


# ---------------------------------------------------------------------------
# Mandatory (ii): typed-subcommand interleave between claim and commit
# ---------------------------------------------------------------------------


class TestInterleavedTypedRow:
    def test_typed_row_between_claim_and_commit_refuses_and_names_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE)

        claim = claim_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert claim.ok

        # Inject a REAL typed-subcommand row via the CLI. CWD == CORTEX_REPO_ROOT
        # (pinned above), so the CWD-based resolver behind the typed subcommand
        # lands it on the same physical log this claim gated on.
        from cortex_command.lifecycle_event import _run

        rc = _run(
            [
                "phase-transition",
                "--feature",
                FEATURE,
                "--from",
                FROM_STATE,
                "--to",
                TO_STATE,
            ]
        )
        assert rc == 0
        assert len(_events(_read_rows(log_path), "phase_transition")) == 1

        commit = commit_transition(FEATURE, FROM_STATE, TO_STATE, inv)
        assert not commit.ok and commit.status == "state-moved"
        # The refusal NAMES the interleaved row.
        assert commit.interleaved_row is not None
        assert commit.interleaved_row.get("event") == "phase_transition"
        assert "state moved since claim" in (commit.reason or "")
        assert "phase_transition" in (commit.reason or "")
        # No advance_committed was written.
        assert _events(_read_rows(log_path), "advance_committed") == []


# ---------------------------------------------------------------------------
# Mandatory (i): two real processes race the same transition
# ---------------------------------------------------------------------------


def _race_worker(
    root_str: str,
    invocation_id: str,
    barrier,
    result_q,
) -> None:
    """Child-process body: claim, rendezvous, then commit iff the claim won.

    The barrier between claim and commit guarantees BOTH processes finish their
    claim attempt before either commits — so the loser reads the winner's
    still-unresolved ``advance_started`` under the flock and is refused
    ("in-flight transition"), rather than the winner racing ahead to commit and
    silently resolving its claim first. Distinct ``invocation_id`` per process
    models two independent advance attempts of the same edge.
    """
    os.environ["CORTEX_REPO_ROOT"] = root_str
    os.chdir(root_str)
    # Re-import inside the (spawned) child.
    from cortex_command.lifecycle_event import (
        claim_transition as _claim,
        commit_transition as _commit,
    )

    claim = _claim(FEATURE, FROM_STATE, TO_STATE, invocation_id)
    try:
        barrier.wait(timeout=30)
    except Exception:  # pragma: no cover - defensive against a hung peer
        pass
    if claim.ok:
        commit = _commit(FEATURE, FROM_STATE, TO_STATE, invocation_id)
        result_q.put((invocation_id, f"claim:{claim.status}", f"commit:{commit.status}"))
    else:
        result_q.put((invocation_id, f"claim:{claim.status}", None))


@pytest.mark.serial
class TestTwoProcessRace:
    def test_exactly_one_commit_one_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_path = _pin_root(tmp_path, monkeypatch)
        inv_a = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE, "proc-a")
        inv_b = derive_invocation_id(FEATURE, FROM_STATE, TO_STATE, "proc-b")
        assert inv_a != inv_b

        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        result_q = ctx.Queue()
        procs = [
            ctx.Process(
                target=_race_worker,
                args=(str(tmp_path), inv, barrier, result_q),
            )
            for inv in (inv_a, inv_b)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0

        results = [result_q.get(timeout=10) for _ in range(2)]

        claim_statuses = sorted(r[1] for r in results)
        commit_statuses = [r[2] for r in results if r[2] is not None]

        # Exactly one process claimed and committed; the other was refused at
        # claim with the in-flight-transition message.
        assert claim_statuses == ["claim:claimed", "claim:in-flight"]
        assert commit_statuses == ["commit:committed"]

        # The durable log bears exactly one advance_committed and exactly one
        # advance_started (the refused claimant wrote nothing).
        rows = _read_rows(log_path)
        assert len(_events(rows, "advance_committed")) == 1
        assert len(_events(rows, "advance_started")) == 1
