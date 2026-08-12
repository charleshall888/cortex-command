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

from cortex_command.common import TERMINAL_STATUSES
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle.resolve import (
    KNOWN_STATES,
    _PHASE_NEXT,
    _ROUTE_NEXT,
    _next_for_route,
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
    """Backlog with one item whose lifecycle_slug names a real lifecycle dir.

    The status is deliberately non-terminal. These tests exercise slug
    remapping, and since #480 a terminal status routes the no-directory arm to
    ``closed`` before it can reach the ``new`` verdict they assert — which
    would make them pass or fail on the fixture's status rather than on the
    remap they are named for. ``refined`` matches the sibling fixture in
    ``test_new_branch_normalizes_numeric_lifecycle_slug``.
    """
    backlog = root / "the-backlog"
    backlog.mkdir()
    (backlog / "308-render-thing.md").write_text(
        "---\ntitle: render thing\nstatus: refined\n"
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


# --- recorded backlog outcome reaches routing (#480) ------------------------

def _outcome_backlog(
    root: Path, monkeypatch: pytest.MonkeyPatch, frontmatter: str
) -> None:
    """One backlog item at id 500 carrying *frontmatter*, no lifecycle dir."""
    backlog = root / "the-backlog"
    backlog.mkdir(exist_ok=True)
    (backlog / "500-parked-thing.md").write_text(
        "---\ntitle: parked thing\n%s---\n" % frontmatter, encoding="utf-8"
    )
    monkeypatch.setenv("CORTEX_BACKLOG_DIR", str(backlog))


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_every_terminal_status_routes_closed_not_new(
    root: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    """A finished item is never served as new work.

    Parametrized over the whole of ``TERMINAL_STATUSES`` rather than a sample:
    the set is hand-maintained and carries legacy spellings (``done``,
    ``won't-do``) that a single-value test would leave unprotected — which is
    how #480 reached production, with ``done`` and ``wontfix`` rows both
    returning "New feature — start the /cortex-core:refine flow at research."
    """
    _outcome_backlog(root, monkeypatch, "status: %s\n" % status)
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "closed"
    assert "refine" not in r["next"]


def test_parked_status_routes_parked_and_is_not_reported_as_finished(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#480's first Edge: parked is distinct from terminal, both in the state
    and in what the directive claims about it."""
    _outcome_backlog(root, monkeypatch, "status: deferred\n")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "parked"
    assert "NOT finished" in r["next"]


def test_deferred_tag_parks_an_otherwise_startable_status(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The older parking spelling is a tag, and it annotates on its own.

    Guards the reason ``_is_deferred`` is imported instead of re-spelled: a
    local ``status == "deferred"`` check would pass every other test here and
    silently miss this item.
    """
    _outcome_backlog(root, monkeypatch, "status: backlog\ntags: ['deferred']\n")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "parked"


def test_terminal_beats_parked_when_an_item_carries_both(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An item parked and later finished is finished, not held."""
    _outcome_backlog(root, monkeypatch, "status: complete\ntags: ['deferred']\n")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "closed"


def test_archiving_the_lifecycle_dir_cannot_defeat_the_check(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#480's fourth Edge: archiving is sanctioned closure hygiene.

    The gate keys on the recorded status, not on where the directory sits, so
    moving it to ``cortex/lifecycle/archive/`` cannot turn a frozen verdict
    back into new work — the pre-fix behaviour for every archived item.
    """
    _outcome_backlog(root, monkeypatch, "status: wontfix\n")
    archived = root / "cortex" / "lifecycle" / "archive" / "parked-thing"
    archived.mkdir(parents=True)
    (archived / "research.md").write_text("# research", encoding="utf-8")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "closed"


def test_a_live_lifecycle_dir_still_routes_by_its_events_log(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#480's second Edge, held as an absence.

    Where a lifecycle exists the events log is authoritative and was already
    correct; the fix must not start overriding it from frontmatter. The
    outcome still rides the envelope as evidence — it just does not route.
    """
    _outcome_backlog(
        root, monkeypatch, "status: complete\nlifecycle_slug: parked-thing\n"
    )
    _feature_dir(root, "parked-thing")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "resume"
    assert r["backlog"]["outcome"] == "closed"


def test_a_startable_item_is_unaffected(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the fix must not park work that nobody parked."""
    _outcome_backlog(root, monkeypatch, "status: backlog\n")
    r = resolve_invocation("500", project_root=root)
    assert r["state"] == "new"
    assert r["backlog"]["outcome"] is None


@pytest.mark.parametrize(
    "frontmatter",
    ["tags: null\n", "tags: 42\n", "tags: [7, null]\n", "status: null\n", ""],
)
def test_malformed_frontmatter_never_crashes_the_resolver(
    root: Path, monkeypatch: pytest.MonkeyPatch, frontmatter: str
) -> None:
    """Exit-0-by-contract holds against unvalidated frontmatter.

    Nothing validates ``status`` or ``tags`` on write, so the outcome reader
    must coerce rather than trust — a non-str tag would otherwise reach the
    predicate's ``.strip()`` and take the whole verb down.
    """
    _outcome_backlog(root, monkeypatch, frontmatter)
    r = resolve_invocation("500", project_root=root)
    assert r["state"] in KNOWN_STATES


# --- rework-cap discriminant (454) -----------------------------------------

def _capped_feature(root: Path, slug: str) -> Path:
    """A lifecycle whose ladder resolves to ``escalated:rework-cap:2``.

    The cycle comes from the ``review_verdict`` row count in events.log; the
    verdict comes from review.md. Two rows + CHANGES_REQUESTED = the cap.
    """
    d = _feature_dir(root, slug)
    (d / "events.log").write_text(
        "".join(
            json.dumps(
                {"event": "review_verdict", "feature": slug,
                 "verdict": "CHANGES_REQUESTED", "cycle": n}
            )
            + "\n"
            for n in (1, 2)
        ),
        encoding="utf-8",
    )
    (d / "review.md").write_text(
        '{"verdict": "CHANGES_REQUESTED", "cycle": 2}\n', encoding="utf-8"
    )
    return d


def test_rework_cap_resume_serves_the_phase_keyed_directive(root: Path) -> None:
    """A capped resume routes on the bare ``escalated`` state but takes its
    ``next`` from the phase-keyed table, so the operator is not told a reviewer
    rejected work no reviewer rejected."""
    _capped_feature(root, "capped")
    r = resolve_invocation("capped", project_root=root)
    assert r["state"] == "resume"
    assert r["route"] == "escalated"  # the discriminant never reaches route
    assert r["phase"] == "escalated:rework-cap:2"
    assert "rework cap" in r["next"]
    assert "REJECTED" not in r["next"]

    # A real reviewer rejection still gets the route-keyed rejection directive.
    d = _feature_dir(root, "rejected")
    (d / "review.md").write_text('{"verdict": "REJECTED", "cycle": 1}\n', encoding="utf-8")
    rj = resolve_invocation("rejected", project_root=root)
    assert rj["route"] == "escalated"
    assert rj["phase"] == "escalated"
    assert "REJECTED" in rj["next"]
    assert rj["next"] != r["next"]


def test_rework_cap_directive_yields_to_an_explicit_phase_override() -> None:
    """The cap discriminant is only trusted when the caller did not override the
    phase: an override decouples ``route`` from the detected phase, so the
    directive must be keyed on the route alone (the bare rejection)."""
    overridden = _next_for_route("escalated", True, "escalated:rework-cap:2")
    assert _ROUTE_NEXT["escalated"] in overridden
    assert "REJECTED" in overridden
    assert _PHASE_NEXT["escalated:rework-cap"] not in overridden
    # The same inputs without the override take the phase-keyed directive.
    assert (
        _next_for_route("escalated", False, "escalated:rework-cap:2")
        == _PHASE_NEXT["escalated:rework-cap"]
    )
    # A bare escalated phase is a rejection at any cycle, and an absent phase
    # (the pre-discriminant call shape) keeps the route-keyed directive.
    assert _next_for_route("escalated", False, "escalated") == _ROUTE_NEXT["escalated"]
    assert _next_for_route("escalated", False) == _ROUTE_NEXT["escalated"]


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
