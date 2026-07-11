"""Tests for cortex-lifecycle-implement-transition — the implement-cluster verb
whose function body encodes the per-batch ``batch_dispatch`` emission and the §4
phase-exit routing (``implement → {review|complete}``, read through the shared
``reduce_lifecycle_state`` reducer).

Root resolution uses the cwd flavor, so the tests ``monkeypatch.chdir(tmp_path)``
(and ``delenv CORTEX_REPO_ROOT``) and scaffold a ``cortex/`` tree there; the real
``log_event`` then resolves and writes the same tree the verb reads for its
presence checks, and the route is computed by the REAL reducer over an on-disk
``events.log`` fixture (not a monkeypatched reducer).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import implement_transition as it


def _scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, feature: str = "feat") -> Path:
    """chdir into a scaffolded cortex/ project root and return the feature dir."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    return feature_dir


def _events_rows(feature_dir: Path) -> list[dict]:
    log = feature_dir / "events.log"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _event_names(feature_dir: Path) -> list[str]:
    return [r["event"] for r in _events_rows(feature_dir)]


def _seed(feature_dir: Path, *rows: dict) -> None:
    """Write on-disk events.log rows so the REAL reducer/presence-check reads them."""
    feature_dir.joinpath("events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _start(criticality: str, tier: str) -> dict:
    """A well-formed lifecycle_start row seeding both reducer axes."""
    return {
        "event": "lifecycle_start",
        "feature": "feat",
        "tier": tier,
        "criticality": criticality,
    }


# ---------------------------------------------------------------------------
# batch mode — batch_dispatch emission
# ---------------------------------------------------------------------------


def test_batch_dispatch_emits_batch_and_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = it.implement_transition(feature="feat", mode="batch", batch=1, tasks=[1, 2])

    assert r["state"] == "dispatched"
    assert r["emitted"] == ["batch_dispatch"]
    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["batch_dispatch"]
    assert rows[0]["batch"] == 1
    assert rows[0]["tasks"] == [1, 2]


def test_batch_mode_requires_batch_and_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = it.implement_transition(feature="feat", mode="batch", batch=None, tasks=None)
    assert r["state"] == "error"
    assert not (feature_dir / "events.log").exists()


def test_batch_dispatch_reinvocation_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    first = it.implement_transition(feature="feat", mode="batch", batch=1, tasks=[1, 2])
    second = it.implement_transition(feature="feat", mode="batch", batch=1, tasks=[1, 2])
    assert first["emitted"] == ["batch_dispatch"]
    assert second["emitted"] == []
    assert _event_names(feature_dir) == ["batch_dispatch"]


def test_second_batch_not_false_skipped_against_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feature runs many batches; batch 2 must still emit even though batch 1's
    batch_dispatch row exists — the guard matches on event+batch."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    it.implement_transition(feature="feat", mode="batch", batch=1, tasks=[1])
    r2 = it.implement_transition(feature="feat", mode="batch", batch=2, tasks=[2, 3])
    assert r2["emitted"] == ["batch_dispatch"]
    batches = [x["batch"] for x in _events_rows(feature_dir) if x["event"] == "batch_dispatch"]
    assert batches == [1, 2]


def test_batch_dispatch_presence_check_is_not_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row merely mentioning batch_dispatch in another field does not suppress
    emission — only a parsed ``event`` match does."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    _seed(feature_dir, {"event": "note", "text": "batch_dispatch pending for batch 1"})
    r = it.implement_transition(feature="feat", mode="batch", batch=1, tasks=[1])
    assert r["emitted"] == ["batch_dispatch"]
    assert _event_names(feature_dir) == ["note", "batch_dispatch"]


# ---------------------------------------------------------------------------
# transition mode — §4 routing (both routes across criticality × tier)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "criticality,tier,expected_route",
    [
        # low/medium + simple → complete
        ("low", "simple", "complete"),
        ("medium", "simple", "complete"),
        # high/critical force review regardless of tier
        ("high", "simple", "review"),
        ("critical", "simple", "review"),
        # complex tier forces review regardless of criticality
        ("low", "complex", "review"),
        ("medium", "complex", "review"),
        ("high", "complex", "review"),
        ("critical", "complex", "review"),
    ],
)
def test_transition_routes_by_criticality_and_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    criticality: str,
    tier: str,
    expected_route: str,
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    _seed(feature_dir, _start(criticality, tier))
    r = it.implement_transition(feature="feat", mode="transition")

    assert r["state"] == expected_route
    assert r["transition_to"] == expected_route
    assert r["tier"] == tier
    assert r["emitted"] == ["phase_transition"]

    row = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"][0]
    assert row["from"] == "implement"
    assert row["to"] == expected_route
    assert row["tier"] == tier


def test_transition_absent_axes_apply_reducer_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean but stateless log (no lifecycle_start) is NOT corrupted; the verb
    applies the reducer defaults (criticality=medium, tier=simple) → complete."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    # No seed at all — missing events.log, reducer returns empty, not corrupted.
    r = it.implement_transition(feature="feat", mode="transition")
    assert r["state"] == "complete"
    assert r["tier"] == "simple"
    row = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"][0]
    assert row["to"] == "complete"
    assert row["tier"] == "simple"


# ---------------------------------------------------------------------------
# transition mode — corrupted-state arm
# ---------------------------------------------------------------------------


def test_transition_corrupted_state_routes_to_review_with_complex_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A torn line (skipped) leaving tier/criticality unknowable makes the
    reduction corrupted; the cautious criticality-matrix.md:26 default routes to
    review and stamps tier=complex."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    # A JSON-unparseable line (skipped) with no valid lifecycle_start → both axes
    # missing AND skipped_lines non-empty → reduction.corrupted is True.
    feature_dir.joinpath("events.log").write_text(
        "{not valid json\n", encoding="utf-8"
    )
    r = it.implement_transition(feature="feat", mode="transition")

    assert r["state"] == "review"
    assert r["transition_to"] == "review"
    assert r["tier"] == "complex"
    # Tolerant read: the seeded torn line is not JSON, so parse only valid rows.
    rows = []
    for line in (feature_dir / "events.log").read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    row = [x for x in rows if x.get("event") == "phase_transition"][0]
    assert row["to"] == "review"
    assert row["tier"] == "complex"


def test_transition_torn_line_but_axes_recovered_is_not_corrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A torn line alongside a valid lifecycle_start recovers both axes, so the
    reduction is NOT corrupted — the real routing rule applies (here → complete)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    feature_dir.joinpath("events.log").write_text(
        json.dumps(_start("low", "simple")) + "\n" + "{torn\n",
        encoding="utf-8",
    )
    r = it.implement_transition(feature="feat", mode="transition")
    assert r["state"] == "complete"
    assert r["tier"] == "simple"


# ---------------------------------------------------------------------------
# transition mode — idempotency + presence-check discrimination
# ---------------------------------------------------------------------------


def test_transition_reinvocation_emits_no_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    _seed(feature_dir, _start("high", "simple"))
    first = it.implement_transition(feature="feat", mode="transition")
    second = it.implement_transition(feature="feat", mode="transition")
    assert first["emitted"] == ["phase_transition"]
    assert second["emitted"] == []
    transitions = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"]
    assert len(transitions) == 1


def test_transition_guard_ignores_earlier_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The feature's log already carries earlier plan->implement transitions under
    the same event name; the implement->complete emission must still fire (the
    guard matches on from/to, not the bare event name)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    _seed(
        feature_dir,
        _start("low", "simple"),
        {"event": "phase_transition", "feature": "feat", "from": "plan", "to": "implement"},
    )
    r = it.implement_transition(feature="feat", mode="transition")
    assert r["emitted"] == ["phase_transition"]
    transitions = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"]
    assert {"from": "plan", "to": "implement"}.items() <= transitions[0].items()
    assert {"from": "implement", "to": "complete"}.items() <= transitions[1].items()


# ---------------------------------------------------------------------------
# Slug guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ""])
def test_unsafe_slug_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _scaffold(tmp_path, monkeypatch)
    r = it.implement_transition(feature=bad, mode="transition")
    assert r["state"] == "error"
    assert list((tmp_path / "cortex" / "lifecycle").rglob("events.log")) == []


# ---------------------------------------------------------------------------
# KNOWN_STATES exhaustiveness + never-crash CLI
# ---------------------------------------------------------------------------


def test_every_state_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = set()

    _scaffold(tmp_path, monkeypatch, feature="f1")
    seen.add(it.implement_transition(feature="f1", mode="batch", batch=1, tasks=[1])["state"])

    fdir2 = _scaffold(tmp_path, monkeypatch, feature="f2")
    _seed(fdir2, _start("low", "simple"))
    seen.add(it.implement_transition(feature="f2", mode="transition")["state"])

    fdir3 = _scaffold(tmp_path, monkeypatch, feature="f3")
    _seed(fdir3, _start("high", "simple"))
    seen.add(it.implement_transition(feature="f3", mode="transition")["state"])

    _scaffold(tmp_path, monkeypatch, feature="f4")
    seen.add(it.implement_transition(feature="../x", mode="transition")["state"])

    assert seen == set(it.KNOWN_STATES)


def test_cli_batch_mode_inferred_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The smoke command: --batch/--tasks with no --mode infers batch mode."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rc = it.main(["--feature", "feat", "--batch", "1", "--tasks", "[1,2]"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "dispatched"
    assert _event_names(feature_dir) == ["batch_dispatch"]


def test_cli_transition_mode_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    _seed(feature_dir, _start("critical", "simple"))
    rc = it.main(["--feature", "feat", "--mode", "transition"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "review"
    assert obj["tier"] == "simple"


def test_cli_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Any exception escaping implement_transition emits a {"state": "error", ...}
    struct and exits 0 — never a traceback."""
    _scaffold(tmp_path, monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(it, "implement_transition", _boom)
    rc = it.main(["--feature", "feat", "--mode", "transition"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "kaboom" in obj["message"]
