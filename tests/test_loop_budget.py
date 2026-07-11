"""Loop-body token budget (epic 371 Phase C, Task 19 / R17).

The interactive lifecycle **loop body** — the always-resident prose the
`/cortex-core:lifecycle` skill loads every session (`skills/lifecycle/SKILL.md`)
— is bounded to **≤ 4000 tokens**. This is a test-gated ceiling, a guardrail
against future bloat as the served next/advance routing accretes, NOT a tight
fit: the R17 line-item map documents *where* each absorbed block landed, and the
budget is deliberately independent of that map.

Scope boundary (why only SKILL.md): the phase references (`plan.md` /
`implement.md` / `review.md` / `complete.md`) are loaded **one at a time** during
Step 3 ("Read only the current phase's reference"), so they are not part of the
resident loop body — SKILL.md is. The dual-source `plugins/cortex-core/` mirror
is byte-identical to the canonical file (enforced by the pre-commit dual-source
drift gate), so measuring the canonical file is sufficient.

Token measurement: this repo does not vendor a BPE tokenizer, so the budget uses
a deterministic, dependency-free approximation — ``ceil(len(text) / 4)`` — the
widely-used ~4-chars-per-token ratio for English prose under cl100k-family
tokenizers. It is intentionally conservative-enough for a *ceiling* guardrail:
the exact token count under any specific model is within a small factor, and the
4000 ceiling carries ample headroom over the current body.
"""

from __future__ import annotations

import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The resident interactive-loop body.
LOOP_BODY = REPO_ROOT / "skills" / "lifecycle" / "SKILL.md"

# The test-gated ceiling (R17). Tokens, not bytes.
TOKEN_CEILING = 4000

# Chars-per-token approximation (cl100k-family English-prose ratio).
_CHARS_PER_TOKEN = 4


def approx_tokens(text: str) -> int:
    """Deterministic, dependency-free token estimate: ``ceil(chars / 4)``.

    Documented approximation (see module docstring) — the budget is a ceiling
    guardrail, so an estimate within a small factor of any specific model's BPE
    count is sufficient; the ample headroom absorbs the approximation error.
    """
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def test_loop_body_within_4k_token_budget() -> None:
    """The resident lifecycle loop body stays at or under the 4000-token ceiling.

    When this fails, extract prose into a situational/phase reference (loaded
    on demand) rather than raising the ceiling — the ceiling is the whole point
    of the guardrail.
    """
    assert LOOP_BODY.is_file(), f"loop body missing: {LOOP_BODY}"
    text = LOOP_BODY.read_text(encoding="utf-8")
    tokens = approx_tokens(text)
    assert tokens <= TOKEN_CEILING, (
        f"lifecycle loop body {LOOP_BODY} is ~{tokens} tokens "
        f"({len(text)} chars), over the {TOKEN_CEILING}-token ceiling "
        f"(delta +{tokens - TOKEN_CEILING}). Extract prose into a phase or "
        f"situational reference (loaded on demand) rather than raising the "
        f"ceiling."
    )


def test_approx_tokens_is_deterministic_and_monotonic() -> None:
    """Anti-vacuous: the estimator is a pure ceil(chars/4), so a longer string
    never estimates fewer tokens and the ratio is exact at the boundary."""
    assert approx_tokens("") == 0
    assert approx_tokens("abcd") == 1
    assert approx_tokens("abcde") == 2  # ceil(5/4)
    assert approx_tokens("x" * 16000) == 4000  # exactly at the ceiling
    assert approx_tokens("x" * 16001) == 4001  # one char over → over budget
