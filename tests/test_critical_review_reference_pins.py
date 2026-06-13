"""Pin test — protect the load-bearing contract literals/designators in the
critical-review reference family.

`skills/critical-review/references/verification-gates.md` carries route-reaction
prose and a user-facing total-failure string that NO existing static gate covers
(`tests/test_skill_section_citations.py` pins only the *lifecycle* references).
A careless trim of these files breaks nothing detectably while silently degrading
review quality. This module pins the smallest *localizing* set that catches a
deletion, rename, or paraphrase of the structure the four SKILL.md pointers and
the orchestrator's exit-code routing depend on.

KNOWN LIMITATION (by design): this guards token *presence*, not the surrounding
reaction *prose*. A paraphrase of an *unpinned* reaction sentence still passes —
the Task-4 one-time hand-diff (exit 0/2/3/4 vs cortex_command/critical_review/
__init__.py) is the backstop for that residual behavioral risk. Deliberately not
pinned but preserved-by-construction: the `## Partial Coverage / Synthesis
Failure Handling` heading (SKILL.md cites the rule by description, not by
designator) and the Step 2c.5 malformed-envelope / record-exclusion prose (out
of the current trim envelope).

Spec: cortex/lifecycle/adversarially-verified-trim-of-critical-review/spec.md
R1, R2, R3.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "skills" / "critical-review" / "SKILL.md"
VERIFICATION_GATES = (
    REPO_ROOT / "skills" / "critical-review" / "references" / "verification-gates.md"
)

# The canonical user-facing all-reviewers-excluded string. It has NO Python
# source-of-truth (unlike the synth-drift string in critical_review/__init__.py),
# so it must survive verbatim in BOTH the SKILL.md inline copy and the
# verification-gates.md reference copy. Asserting the SAME constant against both
# files IS the cross-file equality guarantee: a paraphrase of either copy fails
# its own substring check, so the two surfaces cannot drift apart undetected.
TOTAL_FAILURE_LITERAL = (
    "All reviewers excluded — drift or Read failure detected; "
    "critical-review pass invalidated. Re-run after resolving "
    "concurrent write source."
)

# Step designators the four SKILL.md pointers (SKILL.md:48, :64, :72, :86)
# structurally depend on. Renumbering any one silently breaks a pointer.
STEP_DESIGNATORS = (
    "## Step 2a.5: Pre-Dispatch (atomic path + SHA pin)",
    "## Step 2c.5: Sentinel-First Verification Gate",
    "## Step 2d.5: Post-Synthesis (atomic SHA verification)",
)

# The exit-2 stop-dispatch reaction in Step 2a.5. prepare-dispatch returns exit 2
# on every path-validation failure (cortex_command/critical_review/__init__.py);
# this stop-the-dispatch reaction is load-bearing route prose.
EXIT2_REACTION = "surface its stderr verbatim to the user and stop"

# Per-subcommand route-reaction markers. Each must appear in BOTH route-table
# sections (Step 2c.5 = check-artifact-stable; Step 2d.5 = check-synth-stable).
EXIT_MARKERS = ("- **Exit 0**", "- **Exit 3**", "- **Exit 4**")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _route_sections(text: str) -> tuple[str, str]:
    """Slice verification-gates.md into the two route-table sections.

    Returns (step_2c5_section, step_2d5_section). Slicing at the Step headings
    is REQUIRED, not optional: each exit marker occurs exactly twice file-wide
    (one per section), so a whole-file `count >= 2` assertion cannot localize a
    single-section deletion — it stays green if a marker is removed from one
    table while the bytes recur elsewhere, or if the two tables are merged.
    """
    h_2c5 = "## Step 2c.5:"
    h_2d5 = "## Step 2d.5:"
    h_partial = "## Partial Coverage"

    i_2c5 = text.index(h_2c5)
    i_2d5 = text.index(h_2d5, i_2c5)
    # Step 2d.5 runs until the Partial Coverage heading (or EOF if absent).
    try:
        i_end = text.index(h_partial, i_2d5)
    except ValueError:
        i_end = len(text)

    section_2c5 = text[i_2c5:i_2d5]
    section_2d5 = text[i_2d5:i_end]
    return section_2c5, section_2d5


# ---------------------------------------------------------------------------
# R1 — total-failure literal (both files) + cross-file equality
# ---------------------------------------------------------------------------

def test_total_failure_literal_in_skill_md() -> None:
    """The total-failure literal must appear verbatim in SKILL.md."""
    assert TOTAL_FAILURE_LITERAL in _read(SKILL_MD), (
        "skills/critical-review/SKILL.md is missing the verbatim total-failure "
        "literal. This user-facing all-reviewers-excluded string has no Python "
        "fallback — restore it byte-for-byte (em-dash and semicolons included) "
        "before changing this file."
    )


def test_total_failure_literal_in_verification_gates() -> None:
    """The total-failure literal must appear verbatim in verification-gates.md."""
    assert TOTAL_FAILURE_LITERAL in _read(VERIFICATION_GATES), (
        "skills/critical-review/references/verification-gates.md is missing the "
        "verbatim total-failure literal (Step 2c.5 total-failure path). Restore "
        "it byte-for-byte before changing this file."
    )


def test_total_failure_literal_cross_file_equality() -> None:
    """The two copies must be byte-identical (both equal the same constant).

    Two independent presence checks against the SAME constant transitively pin
    equality: if either copy is paraphrased, that file's check fails, so the two
    surfaces cannot drift apart silently.
    """
    skill_has = TOTAL_FAILURE_LITERAL in _read(SKILL_MD)
    gates_has = TOTAL_FAILURE_LITERAL in _read(VERIFICATION_GATES)
    assert skill_has and gates_has, (
        "The SKILL.md and verification-gates.md copies of the total-failure "
        "literal have drifted — one no longer matches the canonical constant in "
        "tests/test_critical_review_reference_pins.py. Re-sync both copies to a "
        "single wording (and update the constant here if the wording is "
        "intentionally changing)."
    )


# ---------------------------------------------------------------------------
# R2 — Step designators
# ---------------------------------------------------------------------------

def test_step_designators_present() -> None:
    """Each Step designator a SKILL.md pointer depends on must be present."""
    text = _read(VERIFICATION_GATES)
    for designator in STEP_DESIGNATORS:
        assert designator in text, (
            f"verification-gates.md is missing the designator '{designator}'. "
            "The four SKILL.md pointers (SKILL.md:48, :64, :72, :86) cite these "
            "Step headings; renumbering or renaming one breaks the pointer. "
            "Update the citing SKILL.md lines in the same change."
        )


# ---------------------------------------------------------------------------
# R2 — exit-2 stop-dispatch reaction
# ---------------------------------------------------------------------------

def test_exit2_stop_dispatch_reaction_present() -> None:
    """The Step 2a.5 exit-2 stop-dispatch reaction must be present."""
    assert EXIT2_REACTION in _read(VERIFICATION_GATES), (
        "verification-gates.md is missing the Step 2a.5 exit-2 reaction "
        f"('{EXIT2_REACTION}'). prepare-dispatch returns exit 2 on every "
        "path-validation failure; this stop-the-dispatch reaction is "
        "load-bearing route prose. Restore it before changing this file."
    )


# ---------------------------------------------------------------------------
# R2 — per-section exit-code route markers
# ---------------------------------------------------------------------------

def test_exit_markers_present_per_section() -> None:
    """Each exit marker must appear in BOTH route-table sections.

    Sliced per-section so a deletion/renumber in either subcommand's table fails
    — a whole-file count cannot localize that (each marker occurs exactly twice).
    """
    section_2c5, section_2d5 = _route_sections(_read(VERIFICATION_GATES))
    for marker in EXIT_MARKERS:
        assert marker in section_2c5, (
            f"verification-gates.md Step 2c.5 (check-artifact-stable) route "
            f"table is missing '{marker}'. Do not delete or renumber the exit "
            "reactions; the orchestrator routes on them."
        )
        assert marker in section_2d5, (
            f"verification-gates.md Step 2d.5 (check-synth-stable) route table "
            f"is missing '{marker}'. Do not delete or renumber the exit "
            "reactions; the orchestrator routes on them."
        )
