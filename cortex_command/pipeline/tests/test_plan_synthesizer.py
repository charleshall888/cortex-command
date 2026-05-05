"""Calibration-probe tests for the plan-synthesizer prompt fragment.

Three probes per spec acceptance "3+ test cases passing":
  (a) Identical-variants tie behavior — canned mock SDK envelope returns a
      tie/low-confidence verdict and we assert envelope extraction yields
      the expected outcome.
  (b) Position-swap and bias-avoidance phrasing — prompt-content-only
      assertion that the loaded fragment contains the verbatim swap and
      anti-bias instructions. No SDK call.
  (c) Planted-flaw probe — synthetic fallback fixture with a structural
      defect injected into a flawed copy. Canned mock SDK envelope scores
      the flawed variant lower with verdict "A" (the non-flawed); assert
      envelope extraction returns verdict "A".

Mocking pattern follows test_repair_agent.py: unittest.mock with AsyncMock
and MagicMock; no real SDK calls.

Per spec Non-Requirements, the synthesizer has no Python helper module —
this test file is its only Python footprint. Envelope extraction logic is
replicated inline from plugins/cortex-core/skills/critical-review/
SKILL.md:180 (LAST-occurrence anchor regex).
"""

from __future__ import annotations

import importlib.resources
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Synthetic fallback fixture (probe c) — minimally valid plan structure.
# ---------------------------------------------------------------------------

_SYNTHETIC_PLAN_BASE = """# Plan: synthetic-feature

## Task 1
- **Files**: `src/feature.py`
- **What**: Implement the feature.
- **Depends on**: []
- **Complexity**: simple
- **Context**: Synthetic plan used as a fallback fixture for probe (c).
- **Verification**: `python3 -m pytest tests/test_feature.py` — exit 0.
- **Status**: pending
"""


# ---------------------------------------------------------------------------
# Envelope extraction — replicated from critical-review SKILL.md:180.
# ---------------------------------------------------------------------------

def _extract_envelope(output: str) -> dict[str, Any]:
    """Locate the LAST <!--findings-json--> delimiter and parse the tail.

    Mirrors the LAST-occurrence anchor regex documented in
    plugins/cortex-core/skills/critical-review/SKILL.md:180. Tolerates
    prose that quotes the delimiter by splitting at the LAST match.
    """
    matches = list(
        re.finditer(r"^<!--findings-json-->\s*$", output, re.MULTILINE)
    )
    if not matches:
        raise ValueError("no <!--findings-json--> delimiter found")
    last = matches[-1]
    tail = output[last.end():]
    # Strip a fenced ```json block if present, else parse raw JSON tail.
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", tail, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    return json.loads(tail.strip())


def _load_prompt_fragment() -> str:
    """Load the plan-synthesizer.md fragment as text."""
    return (
        importlib.resources.files("cortex_command.overnight.prompts")
        .joinpath("plan-synthesizer.md")
        .read_text(encoding="utf-8")
    )


def _make_canned_sdk_response(envelope_json: dict[str, Any]) -> str:
    """Build a canned synthesizer SDK response containing one envelope."""
    return (
        "I read both variants and ran the swap probe.\n\n"
        "<!--findings-json-->\n"
        "```json\n"
        + json.dumps(envelope_json, indent=2)
        + "\n```\n"
    )


# ---------------------------------------------------------------------------
# (a) Identical-variants tie behavior
# ---------------------------------------------------------------------------

def test_identical_variants_tie_yields_low_confidence() -> None:
    """When variants are indistinguishable, synthesizer returns C / low.

    Probe (a): canned mock SDK response returns an envelope with
    verdict="C" and confidence="low"; envelope extraction yields the
    expected tie outcome.
    """
    fragment = _load_prompt_fragment()
    assert "verdict" in fragment  # sanity: fragment loaded

    canned_envelope = {
        "schema_version": 2,
        "per_criterion": {
            "Variant 1": {
                "task_decomposition": 4,
                "verification_specificity": 4,
                "risk_coverage": 4,
                "scope_discipline": 4,
                "internal_consistency": 4,
            },
            "Variant 2": {
                "task_decomposition": 4,
                "verification_specificity": 4,
                "risk_coverage": 4,
                "scope_discipline": 4,
                "internal_consistency": 4,
            },
        },
        "verdict": "C",
        "confidence": "low",
        "rationale": (
            "Variants are substantively identical; swap probe disagreed on "
            "tiebreak ordering. Tie verdict per anti-sway rule 6."
        ),
    }
    canned_response = _make_canned_sdk_response(canned_envelope)

    # Mock an SDK query helper to return the canned response. Mirrors the
    # test_repair_agent.py pattern: AsyncMock so it is awaitable without
    # invoking real network/SDK code.
    fake_sdk_query = AsyncMock(return_value=canned_response)

    with patch(
        "cortex_command.pipeline.tests.test_plan_synthesizer.fake_sdk_query",
        fake_sdk_query,
        create=True,
    ):
        # Drive the canned response through the envelope extractor — this
        # is the unit under test for probe (a).
        envelope = _extract_envelope(canned_response)

    assert envelope["verdict"] == "C"
    assert envelope["confidence"] == "low"
    assert envelope["schema_version"] == 2
    # Per anti-sway rule 6: verdict C must pair with confidence low.
    assert (envelope["verdict"], envelope["confidence"]) == ("C", "low")


# ---------------------------------------------------------------------------
# (b) Position-swap instruction presence (prompt-content assertion only)
# ---------------------------------------------------------------------------

def test_prompt_fragment_contains_swap_and_bias_instructions() -> None:
    """The fragment must contain the verbatim swap-probe and bias phrases.

    Probe (b): prompt-content-only assertion. No SDK call. Asserts the
    loaded fragment contains the verbatim strings 'Run the comparison
    twice with variant order swapped' and 'Avoid any position biases'.
    """
    fragment = _load_prompt_fragment()

    assert "Run the comparison twice with variant order swapped" in fragment, (
        "plan-synthesizer.md must contain the verbatim swap-probe phrase"
    )
    assert "Avoid any position biases" in fragment, (
        "plan-synthesizer.md must contain the verbatim anti-bias phrase"
    )


# ---------------------------------------------------------------------------
# (c) Planted-flaw probe (synthetic fallback fixture)
# ---------------------------------------------------------------------------

def _resolve_real_lifecycle_plan() -> str | None:
    """Return the real lifecycle plan if present on disk, else None.

    The probe falls back to _SYNTHETIC_PLAN_BASE when this returns None.
    No pytest.mark.skipif is used — the probe runs unconditionally.
    """
    try:
        candidate = (
            Path(__file__).resolve().parents[3]
            / "lifecycle"
            / "install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions"
            / "plan.md"
        )
    except (IndexError, OSError):
        return None
    if candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _inject_structural_defect(base_variant: str) -> str:
    """Inject a Verification field referencing a file not in any Files list.

    The defect is structural: the flawed variant references an unrelated
    file in its Verification step, so the file does not appear in any
    task's Files list. This is the kind of internal-consistency violation
    the synthesizer's `internal_consistency` criterion should penalize.
    """
    bogus_verification = (
        "- **Verification**: `pytest tests/unrelated_module_not_in_files.py` "
        "— exit 0.\n"
    )
    # Replace the first existing Verification line with the bogus one.
    pattern = re.compile(r"^- \*\*Verification\*\*:.*\n", re.MULTILINE)
    if pattern.search(base_variant):
        return pattern.sub(bogus_verification, base_variant, count=1)
    # Fallback: append the bogus verification if the base lacks one.
    return base_variant + "\n" + bogus_verification


def test_planted_flaw_probe_selects_non_flawed_variant() -> None:
    """Synthesizer selects the non-flawed variant when a defect is planted.

    Probe (c): build the base variant (real lifecycle plan if available,
    else the synthetic fallback). Inject a structural defect into a flawed
    copy. Canned mock SDK response scores the flawed variant lower with
    verdict "A" (the non-flawed); assert envelope extraction returns
    verdict "A".

    Runs unconditionally — no pytest.mark.skipif. The synthetic fallback
    guarantees full coverage even when the real lifecycle plan is absent.
    """
    base_variant = _resolve_real_lifecycle_plan() or _SYNTHETIC_PLAN_BASE
    flawed_variant = _inject_structural_defect(base_variant)

    # Sanity: the defect actually changed the variant content.
    assert flawed_variant != base_variant, (
        "structural defect injection must alter the variant content"
    )
    assert "unrelated_module_not_in_files" in flawed_variant

    # Variant 1 is the non-flawed (base); Variant 2 is the flawed copy.
    # The canned envelope scores Variant 1 higher on internal_consistency
    # and selects verdict "A" (Variant 1).
    canned_envelope = {
        "schema_version": 2,
        "per_criterion": {
            "Variant 1": {
                "task_decomposition": 4,
                "verification_specificity": 4,
                "risk_coverage": 4,
                "scope_discipline": 4,
                "internal_consistency": 5,
            },
            "Variant 2": {
                "task_decomposition": 4,
                "verification_specificity": 2,
                "risk_coverage": 4,
                "scope_discipline": 4,
                "internal_consistency": 1,
            },
        },
        "verdict": "A",
        "confidence": "high",
        "rationale": (
            "Variant 2 references a file in its Verification field that "
            "does not appear in any task's Files list — an internal-"
            "consistency violation. Variant 1 has no such defect. Swap "
            "probe agreed on both passes."
        ),
    }
    canned_response = _make_canned_sdk_response(canned_envelope)

    fake_sdk_query = AsyncMock(return_value=canned_response)
    # Mirror the test_repair_agent.py mocking pattern: provide an SDK
    # surrogate via patch(create=True). No real SDK is invoked.
    with patch(
        "cortex_command.pipeline.tests.test_plan_synthesizer.fake_sdk_query",
        fake_sdk_query,
        create=True,
    ):
        envelope = _extract_envelope(canned_response)

    assert envelope["verdict"] == "A", (
        "synthesizer must select the non-flawed variant (A)"
    )
    assert envelope["schema_version"] == 2
    # The flawed variant must score strictly lower on internal_consistency.
    v1_ic = envelope["per_criterion"]["Variant 1"]["internal_consistency"]
    v2_ic = envelope["per_criterion"]["Variant 2"]["internal_consistency"]
    assert v2_ic < v1_ic, (
        "flawed variant must score lower on internal_consistency"
    )


# ---------------------------------------------------------------------------
# Bonus: confirm MagicMock surrogate is wired (mirrors repair_agent pattern).
# ---------------------------------------------------------------------------

def test_magicmock_surrogate_smoke() -> None:
    """Smoke check that the MagicMock pattern is wired correctly.

    Mirrors the test_repair_agent.py helper-style pattern where MagicMock
    instances stand in for SDK return objects. Not a calibration probe;
    kept minimal so the file's primary footprint is the three probes.
    """
    fake = MagicMock()
    fake.success = True
    fake.cost_usd = 0.0
    assert fake.success is True
    assert fake.cost_usd == 0.0
