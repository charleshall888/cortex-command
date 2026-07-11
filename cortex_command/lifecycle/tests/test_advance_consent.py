"""Task 14b — advance's consent cross-checks (hazard 5, fabricated-attestation defense).

Two obligations bolt onto Task 14's ``_consent_cross_check`` seam and the emission
plan:

  * **Merge-consent gh PR-state cross-check** — a merge-consent transition
    (``review.approved``, review→complete) whose feature carries a recorded PR
    cross-checks REAL gh PR state via an injectable subprocess seam
    (:func:`advance._run_gh` / the ``gh_run`` inject). A PR that gh reports is NOT
    merged refuses the transition; a MERGED PR proceeds; an unverifiable gh (no PR
    recorded, gh off PATH, non-zero exit) fails OPEN — the check hardens an existing
    merge claim, it never invents a PR requirement. Every test injects the seam so
    NO network is touched (the mismatch-refusal path is exercised with a mocked gh
    reporting a definite non-merged state — never a permissive stub that can only
    pass).
  * **Quoted-utterance payload** — the operator's verbatim consent text lands
    field-additively (``consent_utterance``) on the ``plan_approved``/``spec_approved``
    rows ONLY, never on ``phase_transition``/``feature_paused``, and is omitted
    entirely when no utterance is supplied (the legacy rows keep their pre-14b shape).

Isolation mirrors ``test_advance.py``: an explicit ``log_path`` under ``tmp_path`` and
phase scaffolds so the claim's from_state gate passes. The gh boundary is ALWAYS
mocked — either by passing ``gh_run=`` directly into the seam or by monkeypatching
``advance._run_gh`` for the end-to-end path.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle import transition_table as tt


# ---------------------------------------------------------------------------
# Fixtures / helpers (mirrors test_advance.py's harness)
# ---------------------------------------------------------------------------


def _feature_dir(tmp_path: Path, feature: str = "feat") -> Path:
    d = tmp_path / "cortex" / "lifecycle" / feature
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(feature_dir: Path) -> Path:
    return feature_dir / "events.log"


def _rows(feature_dir: Path) -> list[dict]:
    log = _log(feature_dir)
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _names(feature_dir: Path) -> list[str]:
    return [r["event"] for r in _rows(feature_dir)]


def _seed(feature_dir: Path, rows: list[dict]) -> None:
    _log(feature_dir).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _row(feature_dir: Path, event: str) -> dict:
    return [r for r in _rows(feature_dir) if r["event"] == event][0]


def _review_phase(fd: Path, *, with_pr: bool = False) -> None:
    """plan.md all-checked + plan_approved → detect_lifecycle_phase == 'review'.
    Optionally seed a ``pr_opened`` row (PR #42, owner/repo) for the cross-check."""
    (fd / "plan.md").write_text("- **Status**: [x] a\n", encoding="utf-8")
    seed = [{"event": "plan_approved", "feature": "feat", "dispatch_choice": "trunk"}]
    if with_pr:
        seed.append({"event": "pr_opened", "feature": "feat", "number": 42,
                     "repo": "owner/repo", "url": "https://github.com/owner/repo/pull/42"})
    _seed(fd, seed)


def _plan_phase(fd: Path) -> None:
    """spec.md + plan.md (unchecked) present, not yet approved → 'plan'."""
    (fd / "spec.md").write_text("s", encoding="utf-8")
    (fd / "plan.md").write_text("- **Status**: [ ] a\n", encoding="utf-8")


def _specify_phase(fd: Path) -> None:
    """research.md + spec.md present, not yet spec_approved → 'specify'."""
    (fd / "research.md").write_text("r", encoding="utf-8")
    (fd / "spec.md").write_text("s", encoding="utf-8")


def _fake_gh(state: str):
    """A subprocess-seam stub returning a gh ``pr view --json state`` payload with
    *state* — the whole point is that NO real subprocess/network runs. Records the
    commands it was handed so a test can assert the seam was actually exercised."""
    calls: list[list[str]] = []

    def _run(cmd: list[str]):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout=json.dumps({"state": state}))

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


_REVIEW_APPROVED = tt.transition_by_id("review.approved")
_PLAN_BRANCH = tt.transition_by_id("plan.branch-mode-approved")
_PR_ROW = {"event": "pr_opened", "feature": "feat", "number": 42, "repo": "owner/repo"}


# ---------------------------------------------------------------------------
# gh cross-check — the seam, exercised directly (subprocess injected, no network)
# ---------------------------------------------------------------------------


def test_cross_check_refuses_when_pr_not_merged(tmp_path: Path) -> None:
    """MANDATORY mismatch-refusal path: a merge-consent transition whose recorded PR
    gh reports as OPEN (definitively NOT merged) is refused — the fabricated-
    attestation defense. The gh boundary is a mocked seam (no network)."""
    gh = _fake_gh("OPEN")
    objection = adv._consent_cross_check(
        verb="review-verdict", transition=_REVIEW_APPROVED, feature="feat",
        log_path=_log(_feature_dir(tmp_path)), rows=[_PR_ROW], gh_run=gh,
    )
    assert objection is not None
    assert "not merged" in objection["reason"]
    assert "#42" in objection["missing_evidence"]
    assert objection["gh_cross_check"] == {
        "number": 42, "repo": "owner/repo", "state": "OPEN", "expected": ["MERGED"],
    }
    # The seam WAS driven (proves the refusal is not a permissive no-op).
    assert gh.calls and gh.calls[0][:3] == ["gh", "pr", "view"]
    assert "--repo" in gh.calls[0] and "owner/repo" in gh.calls[0]


def test_cross_check_passes_when_pr_merged(tmp_path: Path) -> None:
    """A recorded PR gh reports as MERGED clears the cross-check (no objection)."""
    gh = _fake_gh("MERGED")
    objection = adv._consent_cross_check(
        verb="review-verdict", transition=_REVIEW_APPROVED, feature="feat",
        log_path=_log(_feature_dir(tmp_path)), rows=[_PR_ROW], gh_run=gh,
    )
    assert objection is None
    assert gh.calls, "the merged PR must still be verified against gh"


def test_cross_check_no_pr_recorded_fails_open(tmp_path: Path) -> None:
    """A merge-consent transition with NO recorded PR (trunk-mode completion) has
    nothing to cross-check — the seam is never called and no objection is raised."""
    gh = _fake_gh("OPEN")  # would refuse IF it were consulted
    objection = adv._consent_cross_check(
        verb="review-verdict", transition=_REVIEW_APPROVED, feature="feat",
        log_path=_log(_feature_dir(tmp_path)), rows=[], gh_run=gh,
    )
    assert objection is None
    assert gh.calls == [], "no PR recorded → gh must not be consulted"


def test_cross_check_gh_unresolvable_fails_open(tmp_path: Path) -> None:
    """When the gh seam cannot produce a verdict (exec failure → None), the check
    fails OPEN — it refuses only on a DEFINITE non-merged state, never a blocked
    network (gh off PATH / offline must not wedge a legitimate completion)."""
    objection = adv._consent_cross_check(
        verb="review-verdict", transition=_REVIEW_APPROVED, feature="feat",
        log_path=_log(_feature_dir(tmp_path)), rows=[_PR_ROW],
        gh_run=lambda cmd: None,
    )
    assert objection is None


def test_cross_check_skips_non_merge_consent_transition(tmp_path: Path) -> None:
    """A non-merge-consent transition (plan.branch-mode-approved) is never cross-
    checked, even with a recorded PR in history — the seam is scoped to
    review→complete only."""
    gh = _fake_gh("OPEN")
    objection = adv._consent_cross_check(
        verb="plan-decision", transition=_PLAN_BRANCH, feature="feat",
        log_path=_log(_feature_dir(tmp_path)), rows=[_PR_ROW], gh_run=gh,
    )
    assert objection is None
    assert gh.calls == []


def test_gh_pr_state_tolerates_bad_gh_output(tmp_path: Path) -> None:
    """The state resolver collapses a non-zero exit / unparseable JSON / missing
    state to None (→ fail open), never a crash."""
    assert adv._gh_pr_state(1, "", run=lambda c: types.SimpleNamespace(
        returncode=1, stdout="")) is None
    assert adv._gh_pr_state(1, "", run=lambda c: types.SimpleNamespace(
        returncode=0, stdout="not json")) is None
    assert adv._gh_pr_state(1, "", run=lambda c: types.SimpleNamespace(
        returncode=0, stdout=json.dumps({}))) is None
    assert adv._gh_pr_state(1, "", run=lambda c: types.SimpleNamespace(
        returncode=0, stdout=json.dumps({"state": "MERGED"}))) == "MERGED"


# ---------------------------------------------------------------------------
# gh cross-check — end-to-end through advance() (monkeypatched subprocess seam)
# ---------------------------------------------------------------------------


def test_advance_refuses_review_approved_when_pr_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: review-verdict APPROVED on a feature whose recorded PR gh reports
    as OPEN refuses BEFORE side effects — no advance_committed, no legacy transition
    row, and the orphaned advance_started stays recoverable by invocation_id. gh is
    mocked at the module seam (no network)."""
    fd = _feature_dir(tmp_path)
    _review_phase(fd, with_pr=True)
    monkeypatch.setattr(adv, "_run_gh", _fake_gh("OPEN"))

    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="APPROVED", cycle=1,
        drift="none", from_state="review", log_path=_log(fd),
    )

    assert r["state"] == "refused"
    assert r["from_state"] == "review" and r["to_state"] == "complete"
    assert r["gh_cross_check"]["state"] == "OPEN"
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]
    names = _names(fd)
    assert "advance_committed" not in names
    assert "review_verdict" not in names  # refused before side effects
    assert names.count("advance_started") == 1  # recoverable orphan


def test_advance_completes_review_approved_when_pr_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: the same transition proceeds to complete when gh reports MERGED."""
    fd = _feature_dir(tmp_path)
    _review_phase(fd, with_pr=True)
    monkeypatch.setattr(adv, "_run_gh", _fake_gh("MERGED"))

    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="APPROVED", cycle=1,
        drift="none", from_state="review", log_path=_log(fd),
    )

    assert r["state"] == "approved" and r["to_state"] == "complete"
    assert r["advanced"] is True
    names = _names(fd)
    assert "review_verdict" in names and "advance_committed" in names


def test_advance_trunk_mode_completion_needs_no_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A review→complete with NO recorded PR completes without consulting gh — a
    trunk-mode completion is never blocked by the merge cross-check."""
    fd = _feature_dir(tmp_path)
    _review_phase(fd, with_pr=False)
    gh = _fake_gh("OPEN")  # would refuse IF consulted
    monkeypatch.setattr(adv, "_run_gh", gh)

    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="APPROVED", cycle=1,
        drift="none", from_state="review", log_path=_log(fd),
    )

    assert r["state"] == "approved" and r["advanced"] is True
    assert gh.calls == [], "no PR → gh must not be consulted"


# ---------------------------------------------------------------------------
# Quoted-utterance payload — field-additive on plan_approved / spec_approved
# ---------------------------------------------------------------------------


def test_plan_approved_carries_consent_utterance(tmp_path: Path) -> None:
    """MANDATORY quoted-utterance emission: a plan-decision with --consent-utterance
    lands the verbatim text on plan_approved ONLY — never on the phase_transition."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    utterance = 'operator said: "yes, dispatch it in trunk mode"'

    r = adv.advance(
        verb="plan-decision", feature="feat", decision="branch-mode-approved",
        dispatch_choice="trunk", from_state="plan", log_path=_log(fd),
        consent_utterance=utterance,
    )

    assert r["advanced"] is True
    plan_approved = _row(fd, "plan_approved")
    assert plan_approved["consent_utterance"] == utterance
    assert plan_approved["dispatch_choice"] == "trunk"  # additive, not a replacement
    # The utterance is NOT smeared onto the transition row.
    assert "consent_utterance" not in _row(fd, "phase_transition")


def test_spec_approved_carries_consent_utterance(tmp_path: Path) -> None:
    """spec-approve/approved lands the utterance on spec_approved, not phase_transition."""
    fd = _feature_dir(tmp_path)
    _specify_phase(fd)
    utterance = 'operator said: "spec looks good, approved"'

    r = adv.advance(
        verb="spec-approve", feature="feat", decision="approved", emit_transition=True,
        from_state="specify", log_path=_log(fd), consent_utterance=utterance,
    )

    assert r["advanced"] is True
    assert _row(fd, "spec_approved")["consent_utterance"] == utterance
    assert "consent_utterance" not in _row(fd, "phase_transition")


def test_wait_approved_utterance_only_on_plan_approved(tmp_path: Path) -> None:
    """wait-approved lands the utterance on plan_approved, never on feature_paused."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)

    adv.advance(
        verb="plan-decision", feature="feat", decision="wait-approved",
        from_state="plan", log_path=_log(fd), consent_utterance="waiting: approved",
    )

    assert _row(fd, "plan_approved")["consent_utterance"] == "waiting: approved"
    assert "consent_utterance" not in _row(fd, "feature_paused")


def test_consent_utterance_omitted_when_absent(tmp_path: Path) -> None:
    """Absent an utterance the field is omitted entirely — the legacy plan_approved
    row keeps its exact pre-14b shape (no null key smuggled in)."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)

    adv.advance(
        verb="plan-decision", feature="feat", decision="branch-mode-approved",
        dispatch_choice="trunk", from_state="plan", log_path=_log(fd),
    )

    assert "consent_utterance" not in _row(fd, "plan_approved")


def test_cli_threads_consent_utterance(tmp_path: Path, capsys) -> None:
    """The --consent-utterance argv reaches the emitted plan_approved row."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    rc = adv.main([
        "plan-decision", "--feature", "feat", "--decision", "branch-mode-approved",
        "--dispatch-choice", "trunk", "--from-state", "plan",
        "--log-path", str(_log(fd)), "--consent-utterance", "cli: approved",
    ])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["state"] == "branch-mode-approved"
    assert _row(fd, "plan_approved")["consent_utterance"] == "cli: approved"
