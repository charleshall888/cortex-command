"""cortex-resolve-model — resolve the lifecycle dispatch model for a (role, criticality).

Owns the deterministic *(role, criticality) → model* Lifecycle Matrix as the
single executable source for the value-bearing lifecycle dispatch roles, so the
skill prose keeps only the role/criticality judgment (policy) and defers the
lookup (mechanism) to this verb. Pure, stdlib-only; it does NOT import from
``cortex_command/pipeline/dispatch.py`` (the SDK pipeline matrix
``resolve_model(complexity, criticality)`` is a structurally different lattice:
``orchestrator-fix``'s ``sonnet|sonnet|sonnet|opus`` row is unrepresentable in
the complexity×criticality pipeline matrix, so the two stay separate).

Usage:
  cortex-resolve-model --role <r> [--criticality <c>]

Roles:
  review, builder, orchestrator-fix, competing-plan  — tier-keyed (need --criticality)
  synthesizer, searcher                                — criticality-independent (no --criticality)

Output:
  Bare model name + newline on stdout, exit 0 on success.

Fail-loud (exit 2 + stderr, never a default):
  - unknown --role / unknown --criticality (rejected by argparse, stderr lists choices)
  - a tier-keyed role with --criticality omitted
  - an undefined (role, criticality) cell (e.g. competing-plan at low/medium/high)

A default would silently mask a typo'd role or a wrong-criticality wiring, so
the verb never substitutes a model — the calling site is expected to halt and
escalate on a nonzero exit.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

# ---------------------------------------------------------------------------
# The Lifecycle Matrix: (role, criticality) -> model, for the tier-keyed roles.
#
# Load-bearing: this is the discriminator that makes --role mandatory. At
# `high`, `builder` resolves to `opus` while `review`/`orchestrator-fix`
# resolve to `sonnet` — a deliberate role threshold (both correct), not drift.
# Because the model differs by role at the same criticality, criticality alone
# cannot determine the model; the role is required. The full design rationale
# (parallel→sonnet, exploration→haiku, etc.) lives in docs/internals/sdk.md.
#
# `review` is deliberately uniform: reviewer agents route to sonnet at every
# criticality (requirements ruling 2026-07-16 — escalation buys reviewer count
# and the opus synthesizer, not a per-reviewer model). The row stays tier-keyed
# so the call-site contract (--criticality required) is stable.
#
# `competing-plan` is critical-gated: it only dispatches at `critical`, so the
# low/medium/high cells are intentionally absent (resolving one is a wiring
# error → exit 2), not filled with a default.
# ---------------------------------------------------------------------------
_LIFECYCLE_MATRIX: dict[str, dict[str, str]] = {
    "review": {"low": "sonnet", "medium": "sonnet", "high": "sonnet", "critical": "sonnet"},
    "builder": {"low": "sonnet", "medium": "sonnet", "high": "opus", "critical": "opus"},
    "orchestrator-fix": {
        "low": "sonnet",
        "medium": "sonnet",
        "high": "sonnet",
        "critical": "opus",
    },
    "competing-plan": {"critical": "sonnet"},
}

# Criticality-independent roles: the model is pinned regardless of criticality.
# Modeled as a separate constant set rather than a matrix row with four
# identical cells: a constant cannot drift, and it removes the empty
# low/medium/high cells a future editor might be tempted to "fill in" (which
# would invent a criticality dependence the role does not have). This is also
# what lets the standalone synthesizer/searcher dispatch sites resolve with no
# lifecycle-state read.
#
# `searcher` routes the interactive research/discovery core-wave (gather) fan-out
# to sonnet: criticality scales the angle count and triggers the adversarial
# wave, not the per-gatherer model, so the gather model is constant. The
# always-last adversarial wave inherits the parent rather than resolving this
# role (the judgment-inherit contract — see docs/internals/sdk.md and ADR-0023).
_CRITICALITY_INDEPENDENT: dict[str, str] = {"synthesizer": "opus", "searcher": "sonnet"}

# Argparse choices: the five role names (four tier-keyed + the independent one).
_ROLE_CHOICES = sorted(set(_LIFECYCLE_MATRIX) | set(_CRITICALITY_INDEPENDENT))
_CRITICALITY_CHOICES = ["low", "medium", "high", "critical"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-resolve-model",
        description=(
            "Resolve the lifecycle dispatch model for a (role, criticality) "
            "from the deterministic Lifecycle Matrix. Prints the bare model "
            "name and exits 0; fails loud (exit 2) on unknown input or an "
            "undefined cell rather than defaulting."
        ),
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=_ROLE_CHOICES,
        help=(
            "Dispatch role. Tier-keyed roles (review, builder, "
            "orchestrator-fix, competing-plan) require --criticality; "
            "synthesizer and searcher are criticality-independent."
        ),
    )
    parser.add_argument(
        "--criticality",
        required=False,
        default=None,
        choices=_CRITICALITY_CHOICES,
        help=(
            "Lifecycle criticality. Required for tier-keyed roles; ignored "
            "for the criticality-independent synthesizer and searcher roles."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for cortex-resolve-model."""
    parser = _build_parser()
    # Invalid --role/--criticality choices and a missing required --role are
    # rejected here by argparse with exit 2 + stderr listing valid values.
    args = parser.parse_args(argv)

    role: str = args.role
    criticality: Optional[str] = args.criticality

    # Criticality-independent role: emit the pinned model regardless of whether
    # --criticality was supplied (so a standalone site resolves with no state).
    if role in _CRITICALITY_INDEPENDENT:
        sys.stdout.write(_CRITICALITY_INDEPENDENT[role] + "\n")
        return 0

    # Tier-keyed role from here on (argparse guarantees role is one of the five).
    row = _LIFECYCLE_MATRIX.get(role)
    if row is None:  # defensive — choices should make this unreachable.
        sys.stderr.write(
            f"cortex-resolve-model: unknown role: {role!r} "
            f"(valid roles: {', '.join(_ROLE_CHOICES)})\n"
        )
        return 2

    if criticality is None:
        sys.stderr.write(
            f"cortex-resolve-model: --criticality is required for role "
            f"{role!r} (one of: {', '.join(_CRITICALITY_CHOICES)})\n"
        )
        return 2

    model = row.get(criticality)
    if model is None:
        sys.stderr.write(
            f"cortex-resolve-model: no model defined for role {role!r} at "
            f"criticality {criticality!r} (defined criticalities for this "
            f"role: {', '.join(sorted(row))})\n"
        )
        return 2

    sys.stdout.write(model + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
