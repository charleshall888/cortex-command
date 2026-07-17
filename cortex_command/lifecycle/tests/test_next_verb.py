"""Tests for cortex-lifecycle-next — the read-only served-state verb (374 R11).

Coverage map (spec R11 / plan Task 13 verification arm e):

  * **per-state envelope** — ``build_served_envelope`` serves a well-formed
    envelope for EVERY transition-table state (including the event-only
    ``cancelled`` the artifact reader cannot itself produce), each carrying the
    legacy display-phase projection field. Well-formedness is asserted against a
    hand-written required-key set, NOT by re-deriving from the table it renders
    from — so a schema regression fails independently.
  * **advisory guard evaluation** — an implement-state envelope with a reduced
    high criticality reports the ``implement.review`` edge as advisory-holding
    and ``implement.complete`` as not — proving the guard is evaluated, not just
    rendered, while staying labeled advisory.
  * **protocol-skew** — a caller expectation outside the served ``PROTOCOL_VERSION``
    short-circuits to ``{"state": "protocol-skew", ...}`` with the remediation
    message (the loop's halt boundary).
  * **resume full path** — ``next_state`` end-to-end over an artifact fixture
    resolves identity, reduces the pinned log, and serves the concrete state.
  * **worktree divergence (R4 second clause)** — from a worktree CWD ``next``
    resolves the MAIN-root log (its advance contract records it) while a
    CWD-resolved legacy append would land in the worktree-local copy; the
    events-derived phase function scan_lifecycle's mismatch detector consumes
    reports the two logs diverge.
  * **house style** — ``main`` always exits 0 and never tracebacks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.common import (
    LifecycleStateReduction,
    detect_lifecycle_phase,
)
from cortex_command.lifecycle import transition_table as tt
from cortex_command.lifecycle.log_resolver import resolve_events_log
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle.next_verb import (
    KNOWN_STATES,
    build_served_envelope,
    main,
    next_state,
)

_SLUG = "374-served-next-advance-loop"

# The served-envelope schema (resume case). Hand-written so a dropped/renamed
# field fails here independently of the table the verb renders from.
_REQUIRED_KEYS = {
    "state",
    "legacy_display_phase",
    "fragment_ref",
    "pause_spec",
    "advance_contract",
    "guards",
    "evidence_trace",
    "protocol",
}


# --- per-state envelope (arm e) --------------------------------------------


@pytest.mark.parametrize("state", sorted(tt.STATE_NAMES))
def test_every_table_state_serves_well_formed_envelope(state: str, tmp_path: Path) -> None:
    """Every transition-table state serves a well-formed envelope carrying the
    legacy display-phase projection field."""
    events_log = tmp_path / "events.log"
    env = build_served_envelope(state=state, events_log=events_log)

    # Required keys present and independently checked.
    assert _REQUIRED_KEYS <= set(env), f"{state}: missing {_REQUIRED_KEYS - set(env)}"
    assert env["state"] == state
    assert isinstance(env["legacy_display_phase"], str) and env["legacy_display_phase"]
    assert env["protocol"] == PROTOCOL_VERSION

    # Advance contract records the physical log path + its from-state.
    ac = env["advance_contract"]
    assert ac["expected_from_state"] == state
    assert ac["log_path"] == str(events_log)
    assert ac["flock_path"].endswith("events.log.lock")

    # Fragment reference is a selector, not inlined content.
    assert env["fragment_ref"]["flavor"] == "selector"
    assert env["fragment_ref"]["state"] == state

    # Guards labeled advisory (hazard 6).
    assert env["guards"]["advisory"] is True
    assert isinstance(env["guards"]["edges"], list)

    # Pause spec is a structured block.
    assert set(env["pause_spec"]) == {"specs", "active", "active_kind"}


def test_served_state_set_matches_table_state_names() -> None:
    """The served (transition-table) subset of KNOWN_STATES equals the closed
    table's state names — a drift tripwire between the two closed sets."""
    served = set(KNOWN_STATES) & tt.STATE_NAMES
    assert served == tt.STATE_NAMES


def test_cancelled_projects_to_complete_legacy_phase(tmp_path: Path) -> None:
    """The event-only terminal ``cancelled`` (no artifact route) projects to the
    nearest legacy terminal, ``complete`` — the one interesting projection,
    pinned independently."""
    env = build_served_envelope(state="cancelled", events_log=tmp_path / "events.log")
    assert env["legacy_display_phase"] == "complete"
    assert env["fragment_ref"]["reference"] is None  # terminal → no fragment doc


# --- advisory guard evaluation ---------------------------------------------


def test_implement_guard_advisory_holds_on_high_criticality(tmp_path: Path) -> None:
    """A reduced high criticality makes the ``implement.review`` edge advisory-
    hold and ``implement.complete`` not — a real evaluation, still advisory."""
    reduction = LifecycleStateReduction(
        state={"criticality": "high", "tier": "simple"}, skipped_lines=()
    )
    env = build_served_envelope(
        state="implement", events_log=tmp_path / "events.log", reduction=reduction
    )
    edges = {e["transition_id"]: e for e in env["guards"]["edges"]}
    assert edges["implement.review"]["holds"] is True
    assert edges["implement.complete"]["holds"] is False
    # Verdict-reading edges never decide read-side (advance reads verdict at act
    # time) — holds stays None even though the edge is served.


def test_review_verdict_guard_holds_is_none_read_side(tmp_path: Path) -> None:
    """Review-gate guards read ``verdict`` (unavailable read-side); their
    advisory ``holds`` is None, never a guess."""
    env = build_served_envelope(state="review", events_log=tmp_path / "events.log")
    edges = {e["transition_id"]: e for e in env["guards"]["edges"]}
    assert edges["review.approved"]["holds"] is None
    assert "verdict" in edges["review.approved"]["reads"]


# --- protocol-skew ----------------------------------------------------------


def test_protocol_skew_when_expectation_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller expectation above the served protocol → protocol-skew envelope
    with the remediation message (loop halt boundary)."""
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MIN", raising=False)
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MAX", raising=False)
    r = next_state(
        _SLUG, expect_min=PROTOCOL_VERSION + 5, expect_max=PROTOCOL_VERSION + 9
    )
    assert r["state"] == "protocol-skew"
    assert r["classification"] == "out-of-range"
    assert r["served_protocol"] == PROTOCOL_VERSION
    assert "protocol skew" in r["remediation"]


def test_no_expectation_skips_skew_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent any expectation the skew check is skipped and the verb serves
    normally (here: a bare-feature-with-no-dir routing state)."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(tmp_path / "no-backlog"))
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MIN", raising=False)
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MAX", raising=False)
    r = next_state("ghost-feature")
    assert r["state"] != "protocol-skew"
    assert r["protocol"] == PROTOCOL_VERSION


# --- resume full path -------------------------------------------------------


def _seed_feature(root: Path, slug: str, artifacts: dict[str, str]) -> Path:
    """Create ``root/cortex/lifecycle/<slug>/`` with the named artifact files."""
    d = root / "cortex" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    for name, body in artifacts.items():
        (d / name).write_text(body, encoding="utf-8")
    return d


@pytest.fixture
def repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "proj").resolve()
    (root / "cortex" / "lifecycle").mkdir(parents=True)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(root / "no-backlog"))
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MIN", raising=False)
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MAX", raising=False)
    return root


_SPEC_APPROVED = '{"event": "spec_approved"}\n'
_PLAN_APPROVED = '{"event": "plan_approved"}\n'


def test_resume_spec_only_serves_plan_state(repo_root: Path) -> None:
    """A feature dir with an approved spec resolves to the ``plan`` state and
    serves the plan envelope pinned to the main-root log."""
    _seed_feature(repo_root, _SLUG, {"spec.md": "# spec\n", "events.log": _SPEC_APPROVED})
    r = next_state(_SLUG)
    assert r["state"] == "plan"
    assert r["legacy_display_phase"] == "plan"
    assert r["feature"] == _SLUG
    assert r["advance_contract"]["log_path"] == str(resolve_events_log(_SLUG))
    # plan state offers the relayed-consent wait pause among its edges.
    slugs = {p["slug"] for p in r["pause_spec"]["specs"]}
    assert "plan-approval" in slugs
    assert "path_overview" in r  # default-on at resume


def test_resume_plan_incomplete_serves_implement(repo_root: Path) -> None:
    """spec.md + a plan.md with an unchecked task resolves to ``implement``."""
    _seed_feature(
        repo_root,
        _SLUG,
        {
            "spec.md": "# spec\n",
            "plan.md": "- Task 1\n  - **Status**: [ ] pending\n",
            "events.log": _PLAN_APPROVED,
        },
    )
    r = next_state(_SLUG)
    assert r["state"] == "implement"


def test_resume_serves_backlog_linkage(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#400: the resolver's backlog match rides on the served resume envelope
    (``backlog.filename``) so Step 2 can thread it into ``cortex-lifecycle-enter``
    instead of passing ``""`` — the write that left index.md tags empty forever.
    Null when the feature has no backlog item."""
    backlog = repo_root / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    (backlog / "350-wild-light.md").write_text(
        "---\ntitle: 'Wild light'\nuuid: 1234\ntags: [2-5d]\n"
        f"lifecycle_slug: {_SLUG}\nstatus: backlog\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))
    _seed_feature(repo_root, _SLUG, {"spec.md": "# spec\n", "events.log": _SPEC_APPROVED})

    r = next_state(_SLUG)
    assert r["state"] == "plan"
    assert r["backlog"]["filename"] == "350-wild-light.md"

    # No-backlog resume: the key is present and null, never absent.
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(repo_root / "no-backlog"))
    r = next_state(_SLUG)
    assert r["backlog"] is None


def test_explain_expands_evidence_trace(repo_root: Path) -> None:
    """--explain adds the guards step to the evidence trace and the explain marker."""
    _seed_feature(repo_root, _SLUG, {"spec.md": "# spec\n", "events.log": _SPEC_APPROVED})
    plain = next_state(_SLUG)
    explained = next_state(_SLUG, explain=True)
    assert explained.get("explain") is True
    steps = {s["step"] for s in explained["evidence_trace"]}
    assert "guards" in steps
    assert "guards" not in {s["step"] for s in plain["evidence_trace"]}


# --- house style: main never tracebacks, always exit 0 ----------------------


def test_main_exit_zero_and_json(
    repo_root: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed_feature(repo_root, _SLUG, {"spec.md": "# spec\n", "events.log": _SPEC_APPROVED})
    rc = main([_SLUG])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "plan"
    assert out["protocol"] == PROTOCOL_VERSION


def test_main_unsafe_slug_is_error_not_traceback(
    repo_root: Path, capsys: pytest.CaptureFixture
) -> None:
    # A traversal slug must resolve to a routing state or error, never crash.
    rc = main(["resume ../escape"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] in KNOWN_STATES


# --- worktree divergence (R4 second acceptance clause, verb level) ----------


def _make_worktree_fixture(root: Path) -> tuple[Path, Path]:
    """Main-repo + linked-worktree fixture (mirrors test_log_resolver)."""
    root = root.resolve()
    main_r = root / "main"
    wt = root / "wt"
    git_dir = main_r / ".git"
    wt_admin = git_dir / "worktrees" / "wt1"
    wt_admin.mkdir(parents=True)
    (wt_admin / "commondir").write_text("../..\n", encoding="utf-8")
    (main_r / "cortex" / "lifecycle").mkdir(parents=True)
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {wt_admin}\n", encoding="utf-8")
    (wt / "cortex" / "lifecycle").mkdir(parents=True)
    return main_r, wt


def test_worktree_next_resolves_main_root_log_and_detector_reports_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From a worktree CWD, ``next`` resolves the MAIN-root log (its advance
    contract records it) while a CWD-resolved legacy append would target the
    worktree-local copy — and the events-derived phase function the scan_lifecycle
    mismatch detector consumes reports the two logs diverge."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(tmp_path / "no-backlog"))
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MIN", raising=False)
    monkeypatch.delenv("CORTEX_LIFECYCLE_PROTOCOL_MAX", raising=False)
    main_r, wt = _make_worktree_fixture(tmp_path)

    # Main-root canonical feature: approved spec → route "plan".
    main_dir = _seed_feature(
        main_r, _SLUG, {"spec.md": "# spec\n", "events.log": '{"event": "spec_approved"}\n'}
    )
    # Worktree-local copy where a CWD append would land: advanced to review by an
    # approved plan whose only task is checked (a divergent state-moving artifact).
    wt_dir = _seed_feature(
        wt,
        _SLUG,
        {
            "spec.md": "# spec\n",
            "plan.md": "- Task 1\n  - **Status**: [x] done\n",
            "events.log": '{"event": "plan_approved"}\n',
        },
    )

    monkeypatch.chdir(wt)
    r = next_state(_SLUG)

    # next served the MAIN-root log and state, not the worktree-local copy.
    main_log = main_r / "cortex" / "lifecycle" / _SLUG / "events.log"
    wt_log = wt / "cortex" / "lifecycle" / _SLUG / "events.log"
    assert r["state"] == "plan"
    assert r["advance_contract"]["log_path"] == str(main_log)
    assert r["advance_contract"]["log_path"] != str(wt_log)
    # The pinned resolver agrees on the main-root path.
    assert resolve_events_log(_SLUG) == main_log

    # The events-derived phase function scan_lifecycle's mismatch detector reads
    # (common.detect_lifecycle_phase) reports the two physical dirs diverge.
    main_phase = detect_lifecycle_phase(main_dir)["route"]
    wt_phase = detect_lifecycle_phase(wt_dir)["route"]
    assert main_phase == "plan"
    assert wt_phase == "review"
    assert main_phase != wt_phase  # the two-log divergence a mismatch detector surfaces
