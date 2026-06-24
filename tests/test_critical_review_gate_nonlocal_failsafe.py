"""Structural regression guard — non-local §3b seed-tier fail-safe (R8 hardening).

Guards the DOCUMENTED RULE and ITS WIRING, not runtime gate behavior.

The §3b critical-review run/skip decision is model-executed prose: the model
reads `specify.md` §3b, reads the lifecycle tier/criticality and the resolved
backlog backend, and decides whether to run or skip the critical-review skill.
A unit test cannot simulate that runtime decision. What it CAN do — and what
this module does — is pin two structural facts so they cannot silently
regress:

  (a) `critical-review-gate.md` DOCUMENTS the non-local seed-tier fail-safe
      rule (mirroring the existing Corrupted State Rule): when the backend is
      non-local and the seed tier may be un-reconciled, treat the feature as
      requiring review rather than skip-silent.

  (b) `specify.md` §3b READS THE BACKEND (`cortex-read-backlog-backend`)
      TEXTUALLY BEFORE the skip decision, so the inline run/skip site has the
      backend value in hand at the point it would otherwise skip-silent (the
      gate-protocol reference is consulted only on the skip branch, so the
      backend read must live at the inline §3b site, not inside the gate ref).

Why this hole exists (the A-class critical-review finding this guards):
  Under a non-local backend, a resume-to-spec (`research.md` already exists →
  refine skips Clarify) feeds the non-local `reconcile-clarify` no in-session
  computed tier and gives it no `--backlog-slug` durable fallback, so the
  monotonic reducer leaves lifecycle state at the `simple/medium` seed. At
  `tier = simple` the Run/Skip Matrix skip-silents — letting a genuinely
  complex/high feature advance un-reviewed. The fail-safe mirrors the
  Corrupted State Rule: an untrustworthy tier requires review, not a skip.
  The local `cortex-backlog` path is immune (its reconcile re-sources
  tier/criticality from backlog frontmatter on resume).

Mirrors the structural-over-markdown idiom in
`tests/test_critical_review_reference_pins.py` (Path read + substring /
ordering assertions over the skill `.md` files).

Spec: cortex/lifecycle/config-driven-backlog-backend-resolver-local/spec.md R8
(criticality-feed decoupling) + the plan Risk "Non-local resume-to-spec can
leave the gate un-ratcheted" closed via Task 11.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

GATE_REF = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "critical-review-gate.md"
)
SPECIFY_REF = REPO_ROOT / "skills" / "lifecycle" / "references" / "specify.md"

# The console-script every consumer resolves the backend through. The fail-safe
# keys on its output (≠ `cortex-backlog`); pinning the token catches a rename or
# a switch to a different resolution mechanism.
BACKEND_READER = "cortex-read-backlog-backend"

# The skip-direction value the seed tier carries — the fail-safe fires precisely
# when the gate would skip-silent at this tier.
SEED_TIER = "simple"

# The resume-to-spec signature: the rule keys on research.md existing (Clarify
# may have been bypassed). Pinning the artifact name keeps the rule tied to the
# documented resume-to-spec condition.
RESUME_SIGNATURE = "research.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) critical-review-gate.md documents the non-local seed-tier fail-safe rule
# ---------------------------------------------------------------------------


def test_gate_ref_documents_nonlocal_seed_tier_rule() -> None:
    """critical-review-gate.md must document the non-local seed-tier fail-safe.

    Structural guard: asserts the documented rule's key tokens are present —
    the rule names the backend reader, the non-local condition, the `simple`
    seed it fires at, and the `research.md` resume-to-spec signature. This
    pins the DOCUMENTED RULE's presence; it does not (and cannot) verify that
    the model applies the rule at runtime.
    """
    text = _read(GATE_REF)

    assert BACKEND_READER in text, (
        f"critical-review-gate.md no longer references `{BACKEND_READER}`. "
        "The non-local seed-tier fail-safe keys on the resolved backend; "
        "restore the rule documenting that a non-local backend at the "
        "`simple` seed requires review rather than skip-silent."
    )
    assert "non-local" in text.lower(), (
        "critical-review-gate.md no longer documents the `non-local` "
        "seed-tier fail-safe rule. Restore the rule (mirroring the Corrupted "
        "State Rule): under a non-local backend, an un-reconciled seed tier "
        "requires review rather than a skip."
    )
    assert SEED_TIER in text, (
        f"critical-review-gate.md no longer names the `{SEED_TIER}` seed tier "
        "in the non-local fail-safe rule. The rule fires precisely when the "
        f"gate would skip-silent at `tier = {SEED_TIER}`."
    )
    assert RESUME_SIGNATURE in text, (
        f"critical-review-gate.md no longer names `{RESUME_SIGNATURE}` as the "
        "resume-to-spec signature in the non-local fail-safe rule. The rule "
        "keys on research.md existing (the signal Clarify may have been "
        "bypassed)."
    )


# ---------------------------------------------------------------------------
# (b) specify.md §3b reads the backend BEFORE the skip decision
# ---------------------------------------------------------------------------


def test_specify_3b_reads_backend_before_skip_decision() -> None:
    """specify.md §3b must read the backend, textually before the skip branch.

    Structural guard: the backend reader (`cortex-read-backlog-backend`) must
    appear within the §3b section AND before the "critical-review gate
    protocol" handoff (the skip branch consults the gate ref, which is reached
    only when skipping). If the backend read drifted after the skip handoff —
    or out of §3b entirely — the inline fail-safe would have no backend value
    in hand at the decision point. This pins the WIRING ORDER, not the model's
    runtime run/skip choice.
    """
    text = _read(SPECIFY_REF)

    # Slice out the §3b section: from its heading to the next sibling heading.
    h_3b = "### 3b. Critical Review"
    h_4 = "### 4. User Approval"
    assert h_3b in text, (
        "specify.md no longer contains the '### 3b. Critical Review' heading; "
        "the §3b inline run/skip decision is the wiring site for the "
        "non-local seed-tier fail-safe."
    )
    i_3b = text.index(h_3b)
    i_end = text.index(h_4, i_3b) if h_4 in text[i_3b:] else len(text)
    section_3b = text[i_3b:i_end]

    assert BACKEND_READER in section_3b, (
        f"specify.md §3b no longer reads the backend via `{BACKEND_READER}`. "
        "The inline §3b site must resolve the backend before deciding to "
        "skip — the gate-protocol reference is consulted only on the skip "
        "branch, so the backend read must live at the inline decision."
    )

    # The backend read must precede the gate-protocol handoff (the skip branch).
    # The handoff is the "critical-review gate protocol" consult line; the
    # backend reader token must appear before it so the inline fail-safe has
    # the value in hand at the point it would otherwise skip-silent.
    handoff_marker = "critical-review gate protocol"
    assert handoff_marker in section_3b, (
        "specify.md §3b no longer hands off to the 'critical-review gate "
        "protocol' on the skip branch; the ordering guard cannot anchor."
    )
    i_backend = section_3b.index(BACKEND_READER)
    i_handoff = section_3b.index(handoff_marker)
    assert i_backend < i_handoff, (
        "specify.md §3b reads the backend AFTER the gate-protocol (skip-branch) "
        "handoff. The backend read must precede the skip decision so the "
        "non-local seed-tier fail-safe can fire before the gate ref is "
        "consulted. Move the `cortex-read-backlog-backend` read above the "
        "gate-protocol handoff line."
    )
