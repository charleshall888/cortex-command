"""Static wiring guard for the three model-resolution contracts + the R8 single-source structure.

Cortex's skill constellation resolves sub-agent models through
`cortex-resolve-model` at three *distinct* call-site contracts that a future
narration collapse could silently merge:

  (i)   **criticality-keyed + halt** — builder/reviewer/orchestrator-fix/
        competing-plan sites resolve `--role <r> --criticality "$(cortex-lifecycle-state
        … --field criticality)"` and HALT on nonzero exit.
  (ii)  **synthesizer no-criticality + halt** — the plan-synthesizer and the
        critical-review synthesizer resolve `--role synthesizer` with NO
        `--criticality` flag and NO lifecycle-state read (standalone
        critical-review may have no lifecycle session to read), and HALT on
        nonzero exit. Collapsing (ii) into (i) would break standalone
        critical-review — this test exists to prevent that merge.
  (iii) **searcher degrade-loud never-halts** — the research fan-out core wave
        resolves `--role searcher` with NO `--criticality` and, on nonzero
        resolve, DEGRADES LOUD (dispatch with no `model:`, warn, never halt).

It also pins the R8 single-source-plus-citation structure landed by Tasks
9a/9c: the `corrupted:true` rule has one canonical definition
(criticality-matrix.md) plus citations, and refine's backend-gated write-back
routing is defined once and referenced from its second site.

DELIBERATELY OUT OF SCOPE (so this gate is honest rather than self-sealing,
mirroring the `test_*_wired` precedent): the *runtime* behavior — whether the
model actually halts, degrades, or omits `--criticality` at dispatch time — is
untestable in a static check and is NOT asserted here. This test pins the
authored strings only. The per-site runnable `model:` bind surviving the
narration collapse is a manual reviewer invariant, not caught here.
"""

from __future__ import annotations

import pathlib


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def _window(text: str, anchor: str, size: int = 500) -> str:
    """Return the `size`-char slice starting at `anchor`; assert anchor present."""
    idx = text.find(anchor)
    assert idx != -1, f"anchor not found: {anchor!r}"
    return text[idx : idx + size]


# ---------------------------------------------------------------------------
# Contract (i): criticality-keyed + halt
# ---------------------------------------------------------------------------

# (relpath, role) for each site that must resolve the model against feature
# criticality and halt on resolve failure.
_CRITICALITY_KEYED_SITES = [
    ("skills/lifecycle/references/implement.md", "builder"),
    ("skills/lifecycle/references/review.md", "review"),
    ("skills/lifecycle/references/orchestrator-review.md", "orchestrator-fix"),
    ("skills/lifecycle/references/competing-plans.md", "competing-plan"),
]


def test_criticality_keyed_sites_bind_role_and_criticality() -> None:
    """Each contract-(i) site chains `--role <r> --criticality "$(cortex-lifecycle-state`."""
    for rel, role in _CRITICALITY_KEYED_SITES:
        text = _read(rel)
        expected = (
            f'--role {role} --criticality "$(cortex-lifecycle-state'
        )
        assert expected in text, (
            f"{rel}: criticality-keyed contract (i) broken — expected the "
            f"model resolve to chain `{expected}…` reading feature criticality"
        )


def test_criticality_keyed_sites_halt_on_resolve_failure() -> None:
    """Each contract-(i) site must HALT (not degrade) on nonzero resolve."""
    for rel, role in _CRITICALITY_KEYED_SITES:
        text = _read(rel)
        win = _window(text, f"--role {role}", size=900)
        assert "halt and escalate" in win, (
            f"{rel}: contract (i) must halt on nonzero cortex-resolve-model exit "
            f"('halt and escalate' near the --role {role} resolve)"
        )


# ---------------------------------------------------------------------------
# Contract (ii): synthesizer no-criticality + halt
# ---------------------------------------------------------------------------

_SYNTHESIZER_SITES = [
    "skills/lifecycle/references/competing-plans.md",
    "skills/critical-review/SKILL.md",
]


def test_synthesizer_sites_resolve_role_without_criticality() -> None:
    """Synthesizer sites resolve `--role synthesizer` with NO `--criticality` chained.

    This is the load-bearing distinction from contract (i): collapsing (ii)
    into (i) — adding a `--criticality`/lifecycle-state read — would break
    standalone critical-review, which may have no lifecycle session to read.
    """
    for rel in _SYNTHESIZER_SITES:
        text = _read(rel)
        assert "cortex-resolve-model --role synthesizer" in text, (
            f"{rel}: expected the synthesizer resolve `cortex-resolve-model "
            f"--role synthesizer`"
        )
        assert "--role synthesizer --criticality" not in text, (
            f"{rel}: contract (ii) violated — synthesizer resolve must NOT chain "
            f"--criticality (that would collapse it into contract (i))"
        )
        win = _window(text, "cortex-resolve-model --role synthesizer", size=600)
        assert "no `--criticality` flag and no lifecycle-state read" in win, (
            f"{rel}: the no-criticality/no-state-read rationale must stay pinned "
            f"beside the synthesizer resolve"
        )


def test_synthesizer_sites_halt_on_resolve_failure() -> None:
    """Both synthesizer sites HALT on nonzero resolve (like contract (i), unlike (iii))."""
    # competing-plans.md phrases it "halt and escalate (per §1b.b)"; the
    # critical-review site phrases it "halt and escalate rather than guessing".
    for rel in _SYNTHESIZER_SITES:
        text = _read(rel)
        win = _window(text, "cortex-resolve-model --role synthesizer", size=900)
        assert "halt and escalate" in win, (
            f"{rel}: contract (ii) must halt on nonzero cortex-resolve-model exit"
        )


# ---------------------------------------------------------------------------
# Contract (iii): searcher degrade-loud never-halts
# ---------------------------------------------------------------------------

_FANOUT = "skills/research/references/fanout.md"


def test_searcher_site_degrades_loud_and_never_halts() -> None:
    """The fanout core wave resolves `--role searcher`, no --criticality, and degrades loud.

    This is the *opposite* failure shape from contracts (i)/(ii): on nonzero
    resolve it must dispatch with no `model:` and warn rather than halt. The
    absence of 'halt and escalate' in the searcher block pins that distinction.
    """
    text = _read(_FANOUT)
    assert "cortex-resolve-model --role searcher" in text, (
        f"{_FANOUT}: expected the core-wave `cortex-resolve-model --role searcher` resolve"
    )
    assert "--role searcher --criticality" not in text, (
        f"{_FANOUT}: contract (iii) is criticality-agnostic — must NOT chain --criticality"
    )
    win = _window(text, "--role searcher", size=500)
    assert "never halting" in win, (
        f"{_FANOUT}: contract (iii) must state the searcher resolve degrades "
        f"loud and never halts"
    )
    assert "degrades loud" in win, (
        f"{_FANOUT}: contract (iii) must name the degrade-loud fallback"
    )
    assert "halt and escalate" not in win, (
        f"{_FANOUT}: contract (iii) must NOT halt-and-escalate — that is the "
        f"contract (i)/(ii) shape; the searcher wave degrades instead"
    )


def test_searcher_entry_point_carries_runnable_bind() -> None:
    """The research entry point (SKILL.md) carries the runnable searcher bind + no-halt.

    fanout.md authors the rule; each consuming entry point carries its own
    runnable resolve. Pin that the research entry point keeps the bind and the
    do-not-halt instruction so the contract survives at the dispatch site.
    """
    text = _read("skills/research/SKILL.md")
    assert "cortex-resolve-model --role searcher" in text, (
        "research SKILL.md must keep the runnable `--role searcher` bind"
    )
    assert "do not halt" in text, (
        "research SKILL.md must keep the degrade-loud, do-not-halt instruction"
    )


def test_discovery_entry_point_points_to_fanout_and_binds_searcher() -> None:
    """Discovery's research dispatch (Task 9b) points to fanout.md and keeps the bind."""
    text = _read("skills/discovery/references/research.md")
    assert "fanout.md" in text, (
        "discovery research.md must reference the canonical fanout.md after 9b"
    )
    assert "cortex-resolve-model --role searcher" in text, (
        "discovery research.md must retain its own runnable searcher bind"
    )


# ---------------------------------------------------------------------------
# R8 single-source structure: corrupted:true (Task 9a)
# ---------------------------------------------------------------------------

_CORRUPTED_CANONICAL = "skills/lifecycle/references/criticality-matrix.md"
_CORRUPTED_CITATIONS = [
    "skills/lifecycle/references/orchestrator-review.md",
    "skills/lifecycle/references/critical-review-gate.md",
    "skills/refine/SKILL.md",
]
# Distinctive fragment of the canonical rule body — must appear exactly once
# across the canonical + all citation sites.
_CORRUPTED_BODY_FRAGMENT = "tier/criticality are unknowable"


def test_corrupted_rule_defined_once_in_canonical() -> None:
    """The canonical corrupted:true rule body lives in criticality-matrix.md."""
    text = _read(_CORRUPTED_CANONICAL)
    assert '`"corrupted": true`' in text
    assert _CORRUPTED_BODY_FRAGMENT in text, (
        f"{_CORRUPTED_CANONICAL} must carry the canonical corrupted:true rule body"
    )


def test_corrupted_rule_body_is_single_sourced() -> None:
    """The canonical rule body appears exactly once across canonical + citations."""
    files = [_CORRUPTED_CANONICAL, *_CORRUPTED_CITATIONS]
    hits = [rel for rel in files if _CORRUPTED_BODY_FRAGMENT in _read(rel)]
    assert hits == [_CORRUPTED_CANONICAL], (
        "the corrupted:true rule body must be single-sourced in "
        f"criticality-matrix.md; found restated in: "
        f"{[h for h in hits if h != _CORRUPTED_CANONICAL]}"
    )


def test_corrupted_citation_sites_point_to_canonical() -> None:
    """Each non-canonical corrupted:true site cites criticality-matrix.md."""
    for rel in _CORRUPTED_CITATIONS:
        text = _read(rel)
        assert "criticality-matrix.md" in text, (
            f"{rel}: must cite the canonical corrupted:true rule in "
            f"criticality-matrix.md rather than restating it"
        )


def test_refine_preserves_site_specific_corrupted_mapping() -> None:
    """refine's corrupted:true mapping stays inline at the §3b gate site.

    Task 9a required the corrupted-state → run-the-gate steer to live inline
    where the state is read, not only in the generic canonical. That site is
    now specify.md §3b itself (the mapping moved there when refine's SKILL.md
    adaptation list was inlined into specify.md).
    """
    text = _read("skills/refine/references/specify.md")
    section_3b = text.split("### 3b.")[1].split("### 4.")[0]
    assert '"corrupted": true' in section_3b and "run the gate" in section_3b, (
        "specify.md §3b must keep the corrupted-state → run-the-gate mapping "
        "inline alongside the criticality-matrix.md citation"
    )


# ---------------------------------------------------------------------------
# R8 single-source structure: backend-gated write-back routing (Task 9c)
# ---------------------------------------------------------------------------

_REFINE = "skills/refine/SKILL.md"


def test_writeback_routing_defined_once_and_referenced() -> None:
    """The backend-gated write-back routing is defined once (Step 3) and referenced (Step 5)."""
    text = _read(_REFINE)
    assert "canonical **backend-gated write-back routing**" in text, (
        "refine Step 3 must define the canonical backend-gated write-back routing"
    )
    assert "Step 3's canonical backend-gated write-back routing" in text, (
        "refine Step 5 must reference Step 3's canonical routing rather than "
        "restating the 3-arm shape"
    )


def test_writeback_preserves_empty_areas_clearing_quirk() -> None:
    """The site-specific empty-`--areas` clearing quirk must survive at its site (:171)."""
    text = _read(_REFINE)
    assert "passing `--areas` with no values clears the list" in text, (
        "the empty-`--areas` clearing quirk must be preserved at its call site "
        "despite the routing single-source"
    )
