"""Tests for cortex-lifecycle-resolve — the Step 1+2 façade verb.

Each test drives ``resolve_invocation`` (the library entry the CLI wraps) and
asserts the discriminated ``state`` and the fields that state carries. The
composition reuses already-tested primitives, so these tests target the
routing/assembly seam, not the primitives' internals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle.resolve import (
    KNOWN_STATES,
    main,
    resolve_invocation,
)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated project root with an empty (absent) backlog dir so backlog
    resolution returns None unless a test populates CORTEX_BACKLOG_DIR."""
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(tmp_path / "no-backlog"))
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    return tmp_path


def _feature_dir(root: Path, slug: str) -> Path:
    d = root / "cortex" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- model-handled / terminal modes ---------------------------------------

def test_empty_arguments_route_to_scan(root: Path) -> None:
    r = resolve_invocation("", project_root=root)
    assert r["state"] == "empty"


def test_prose_first_word_routes_to_derive_slug(root: Path) -> None:
    # First word "Add" has an uppercase char, so it is not a valid slug ->
    # the parser flags prose needing model-side slug derivation.
    r = resolve_invocation("Add a dark mode toggle please", project_root=root)
    assert r["state"] == "derive-slug"
    assert r["arguments"] == "Add a dark mode toggle please"


def test_bare_phase_token_needs_feature(root: Path) -> None:
    r = resolve_invocation("plan", project_root=root)
    assert r["state"] == "needs-feature"
    assert r["phase"] == "plan"


def test_reserved_verb_without_target_is_error(root: Path) -> None:
    r = resolve_invocation("wontfix", project_root=root)
    assert r["state"] == "error"


def test_wontfix_with_slug_returns_halt_directive(root: Path) -> None:
    r = resolve_invocation("wontfix my-feature", project_root=root)
    assert r["state"] == "wontfix"
    assert r["feature"] == "my-feature"
    assert "cortex-lifecycle-wontfix my-feature" in r["next"]


# --- resume / feature resolution ------------------------------------------

def test_resume_nonexistent_dir_is_no_such_lifecycle(root: Path) -> None:
    r = resolve_invocation("resume ghost", project_root=root)
    assert r["state"] == "no-such-lifecycle"
    assert r["feature"] == "ghost"


def test_bare_feature_with_no_dir_is_new(root: Path) -> None:
    r = resolve_invocation("brand-new-thing", project_root=root)
    assert r["state"] == "new"
    assert r["phase"] == "research"
    assert r["backlog"] is None


def test_existing_lifecycle_resumes_with_composed_state(root: Path) -> None:
    d = _feature_dir(root, "in-flight")
    (d / "research.md").write_text("# research", encoding="utf-8")
    (d / "spec.md").write_text("# spec", encoding="utf-8")
    # spec->plan is gated on a spec_approved EVENT, not just spec.md presence.
    (d / "events.log").write_text(
        json.dumps(
            {"event": "lifecycle_start", "feature": "in-flight",
             "criticality": "high", "tier": "complex"}
        )
        + "\n"
        + json.dumps({"event": "spec_approved", "feature": "in-flight"})
        + "\n",
        encoding="utf-8",
    )
    r = resolve_invocation("in-flight", project_root=root)
    assert r["state"] == "resume"
    assert r["route"] == "plan"  # spec approved, no plan.md yet
    assert r["criticality"] == "high"
    assert r["tier"] == "complex"
    assert "staleness" in r and "spec_age_days" in r["staleness"]
    assert r["phase_override"] is False
    assert "Plan" in r["next"]


def test_explicit_phase_override_wins_over_detection(root: Path) -> None:
    d = _feature_dir(root, "override-me")
    (d / "research.md").write_text("# research", encoding="utf-8")
    (d / "spec.md").write_text("# spec", encoding="utf-8")
    r = resolve_invocation("override-me review", project_root=root)
    assert r["state"] == "resume"
    assert r["route"] == "review"  # honored the explicit phase, not detected 'plan'
    assert r["phase_override"] is True
    assert "override" in r["next"].lower()


def test_ambiguous_backlog_surfaces_candidates(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog = root / "the-backlog"
    backlog.mkdir()
    (backlog / "001-foo-bar.md").write_text(
        "---\ntitle: foo bar\n---\n", encoding="utf-8"
    )
    (backlog / "002-foo-baz.md").write_text(
        "---\ntitle: foo baz\n---\n", encoding="utf-8"
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))
    r = resolve_invocation("foo", project_root=root)
    assert r["state"] == "ambiguous-backlog"
    assert len(r["candidates"]) == 2


def test_unique_backlog_match_attaches_metadata(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog = root / "the-backlog"
    backlog.mkdir()
    (backlog / "042-solo-item.md").write_text(
        "---\ntitle: solo item\n---\n", encoding="utf-8"
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))
    r = resolve_invocation("042", project_root=root)
    assert r["state"] == "new"
    assert r["backlog"]["filename"] == "042-solo-item.md"


# --- contract guards -------------------------------------------------------

def test_every_returned_state_is_in_known_states(root: Path) -> None:
    """Sweep the reachable inputs; every emitted state must be declared."""
    d = _feature_dir(root, "exists")
    (d / "spec.md").write_text("# spec", encoding="utf-8")
    for arg in ["", "prose words here", "plan", "wontfix", "wontfix x",
                "resume ghost", "brand-new", "exists", "exists plan"]:
        state = resolve_invocation(arg, project_root=root)["state"]
        assert state in KNOWN_STATES, f"{arg!r} -> undeclared state {state!r}"


def test_cli_emits_single_json_object(capsys: pytest.CapSys) -> None:
    rc = main([""])
    assert rc == 0
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert obj["state"] == "empty"
