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

from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
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


def test_trailing_non_phase_tokens_ride_as_ignored_tokens(root: Path) -> None:
    """#402: trailing natural language is never a phase override — the struct
    resolves as if it were absent, and the dropped tokens ride the struct as
    ``ignored_tokens`` evidence."""
    _feature_dir(root, "in-flight")
    r = resolve_invocation("in-flight resume implementing", project_root=root)
    assert r["state"] == "resume"
    assert r["feature"] == "in-flight"
    assert r["ignored_tokens"] == ["resume", "implementing"]
    # A clean invocation never carries the key.
    assert "ignored_tokens" not in resolve_invocation("in-flight", project_root=root)


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


# --- numeric-ID -> lifecycle_slug remap (#370) ------------------------------

def _slugged_backlog(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Backlog with one item whose lifecycle_slug names a real lifecycle dir."""
    backlog = root / "the-backlog"
    backlog.mkdir()
    (backlog / "308-render-thing.md").write_text(
        "---\ntitle: render thing\nstatus: complete\n"
        "lifecycle_slug: render-thing-lifecycle\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))


def test_numeric_id_with_existing_slug_dir_resumes(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#370: a numeric ID whose backlog item names an existing slug-keyed
    lifecycle dir must resolve resume under the slug, never state:new."""
    _slugged_backlog(root, monkeypatch)
    d = _feature_dir(root, "render-thing-lifecycle")
    (d / "research.md").write_text("# research", encoding="utf-8")
    r = resolve_invocation("308", project_root=root)
    assert r["state"] == "resume"
    assert r["feature"] == "render-thing-lifecycle"
    assert r["resolved_from"] == "308"


def test_explicit_resume_numeric_id_remaps_to_slug(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#370 Edges: the explicit-resume arm shares the remap — no more
    no-such-lifecycle for a numeric ID whose slug dir exists."""
    _slugged_backlog(root, monkeypatch)
    _feature_dir(root, "render-thing-lifecycle")
    r = resolve_invocation("resume 308", project_root=root)
    assert r["state"] == "resume"
    assert r["feature"] == "render-thing-lifecycle"


def test_numeric_id_without_slug_dir_stays_new(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """True-new preserved: backlog match with lifecycle_slug but no dir on
    disk under either key still resolves state:new (#370's edge, R9).

    #379 R8/R12: the envelope now names the item by its canonical slug with
    ``resolved_from`` carrying the raw token — only ``feature``'s value and
    ``resolved_from``'s presence change; the state does not.
    """
    _slugged_backlog(root, monkeypatch)
    r = resolve_invocation("308", project_root=root)
    assert r["state"] == "new"
    assert r["feature"] == "render-thing-lifecycle"
    assert r["resolved_from"] == "308"


def test_new_branch_normalizes_numeric_lifecycle_slug(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#378 coercion holds on the new branch: an unquoted numeric
    lifecycle_slug read as int is str-coerced before it reaches ``feature``."""
    backlog = root / "the-backlog"
    backlog.mkdir()
    (backlog / "374-numeric-slug.md").write_text(
        "---\ntitle: numeric slug\nstatus: refined\nlifecycle_slug: 374\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))
    r = resolve_invocation("numeric-slug", project_root=root)
    assert r["state"] == "new"
    assert r["feature"] == "374"
    assert r["resolved_from"] == "numeric-slug"


def test_new_branch_without_backlog_match_keeps_caller_token(root: Path) -> None:
    """#379 R10 — Context B: with no backlog match, ``feature`` stays the
    caller's token and no ``resolved_from`` is emitted."""
    r = resolve_invocation("some-adhoc-slug-with-no-item", project_root=root)
    assert r["state"] == "new"
    assert r["feature"] == "some-adhoc-slug-with-no-item"
    assert r["backlog"] is None
    assert "resolved_from" not in r


def test_new_branch_slug_equal_to_token_emits_no_resolved_from(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#379 R11: the normalization fires only when slug != token, so a caller
    already naming the canonical slug gets a byte-identical envelope."""
    _slugged_backlog(root, monkeypatch)
    r = resolve_invocation("render-thing-lifecycle", project_root=root)
    assert r["state"] == "new"
    assert r["feature"] == "render-thing-lifecycle"
    assert "resolved_from" not in r


def test_remap_threads_phase_override(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _slugged_backlog(root, monkeypatch)
    _feature_dir(root, "render-thing-lifecycle")
    r = resolve_invocation("308 review", project_root=root)
    assert r["state"] == "resume"
    assert r["route"] == "review"
    assert r["phase_override"] is True


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


def test_cli_payload_carries_protocol_field(capsys: pytest.CapSys) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    rc = main([""])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION
