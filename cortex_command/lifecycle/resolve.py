"""cortex-lifecycle-resolve — one read-only call that resolves a
``/cortex-core:lifecycle`` invocation to a single actionable struct.

This is the façade over the four primitives the lifecycle skill's Step 1+2
used to invoke back-to-back in prose (parse-args → resolve-backlog-item →
detect-phase → staleness/state). It composes them and returns ONE JSON object
whose ``state`` discriminates the case and whose ``next`` states the single
action the skill should take — so the skill body no longer enumerates every
mode × sub-procedure. Routing lives here (a structural gate) rather than in
prose the model must read past on every invocation.

Read-only by contract: it never writes. The mutating Step-2 sub-procedures
(session registration, init-ensure, backlog write-back, index creation) remain
separate skill steps that run AFTER this resolves.

Emits one JSON object on stdout, always exit 0 — a routing ``state`` is not an
error. ``state`` is one of the closed set in ``KNOWN_STATES``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import (
    _backlog_dir,
    _build_json,
    _item_title,
    _parse_frontmatter,
    resolve,
)
from cortex_command.common import (
    lifecycle_staleness,
    read_criticality,
    read_tier,
    resolve_lifecycle_phase,
)
from cortex_command.lifecycle.parse_args import parse
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION

# Closed set of ``state`` values, asserted for coverage by the test suite.
KNOWN_STATES = (
    "derive-slug",
    "empty",
    "needs-feature",
    "error",
    "wontfix",
    "no-such-lifecycle",
    "ambiguous-backlog",
    "new",
    "resume",
)

# route -> the single next action, phrased as a directive to the skill. The
# skill acts on ``next`` and does not re-derive routing from ``route``.
_ROUTE_NEXT = {
    "research": "Enter Research (delegated to /cortex-core:refine).",
    "specify": "Enter Specify (delegated to /cortex-core:refine).",
    "plan": "Read the plan.md reference and enter Plan.",
    "implement": "Read the implement.md reference and enter Implement.",
    "implement-rework": (
        "review.md is CHANGES_REQUESTED — re-enter Implement to address the feedback."
    ),
    "review": "Read the review.md reference and enter Review.",
    "complete": (
        "Feature is done (feature_complete logged or review APPROVED) — enter Complete."
    ),
    "escalated": (
        "review.md is REJECTED — present the reviewer analysis and ask the user for direction."
    ),
}


def _next_for_route(route: str, phase_overridden: bool) -> str:
    base = _ROUTE_NEXT.get(route, f"Enter the {route} phase.")
    if phase_overridden:
        return base + " (explicit phase override — warn if prerequisite artifacts are missing.)"
    return base


def _resolve_backlog(feature: str) -> Optional[dict]:
    """Read-only backlog resolution. Returns the metadata dict on a unique
    match, ``{"ambiguous": [...]}`` on multiple, or ``None`` when there is no
    match or no backlog directory (the feature simply has no backlog file)."""
    backlog_dir = _backlog_dir()
    if not backlog_dir.is_dir():
        return None
    res = resolve(feature, backlog_dir)
    if res.status == "ok" and res.item is not None:
        return _build_json(res.item, _parse_frontmatter(res.item))
    if res.status == "ambiguous":
        return {
            "ambiguous": [
                {"filename": p.name, "title": _item_title(p, _parse_frontmatter(p))}
                for p in res.candidates[:5]
            ]
        }
    return None


def resolve_invocation(arguments: str, project_root: Optional[Path] = None) -> dict:
    """Classify + resolve a raw ``$ARGUMENTS`` string into one action struct."""
    root = project_root or Path.cwd()
    lifecycle_base = root / "cortex" / "lifecycle"

    parsed = parse(arguments)
    mode = parsed["mode"]
    feature = parsed["feature"]
    phase_override = parsed["phase"]

    # Modes the verb cannot resolve to a phase — hand the skill the directive.
    if mode == "needs-derivation":
        return {
            "state": "derive-slug",
            "arguments": arguments,
            "next": (
                "First word is prose, not a slug. Derive a 3–6 word kebab-case slug "
                "summarizing its intent, announce it as you create "
                "cortex/lifecycle/<slug>/, then re-run resolve on the slug."
            ),
        }
    if mode == "empty":
        return {
            "state": "empty",
            "next": (
                "No feature given. Scan cortex/lifecycle/* for incomplete lifecycles "
                "and offer them (empty-arguments fallback)."
            ),
        }
    if mode == "phase":
        return {
            "state": "needs-feature",
            "phase": phase_override,
            "next": (
                f"Bare phase '{phase_override}' has no feature. Ask the user to name "
                "one; do not create a lifecycle."
            ),
        }
    if mode == "error":
        return {
            "state": "error",
            "next": "A reserved verb was given with no target. Report it needs a feature and stop.",
        }
    if mode == "wontfix":
        return {
            "state": "wontfix",
            "feature": feature,
            "next": (
                f'Run `cortex-lifecycle-wontfix {feature} --reason "<short rationale>"`, '
                "report its outcome, and halt — do not fall through."
            ),
        }

    # feature / resume / complete: resolve to a concrete lifecycle state.
    feature_dir = lifecycle_base / feature
    dir_exists = feature_dir.is_dir()

    # Backlog resolution runs before the resume/new guards: lifecycle dirs are
    # slug-keyed, never numeric-ID-keyed, so a numeric/alias token must remap
    # to the backlog item's lifecycle_slug before any dir-existence verdict
    # (#370 — the slug is the canonical identity; other tokens are input
    # normalization).
    backlog = _resolve_backlog(feature)
    if isinstance(backlog, dict) and "ambiguous" in backlog:
        return {
            "state": "ambiguous-backlog",
            "feature": feature,
            "candidates": backlog["ambiguous"],
            "next": (
                "Present the candidates via AskUserQuestion; re-run resolve on the "
                "chosen slug."
            ),
        }

    resolved_from = None
    if not dir_exists and isinstance(backlog, dict):
        slug = backlog.get("lifecycle_slug")
        # Defensive reader coercion (#378 req-3): a numeric lifecycle_slug read
        # as int must not reach the `lifecycle_base / slug` path-join below
        # (Path / int raises TypeError). Coerce a non-None value to str; the
        # None sentinel stays None (falsy, so the guard skips the remap).
        if slug is not None:
            slug = str(slug)
        if slug and slug != feature and (lifecycle_base / slug).is_dir():
            resolved_from = feature
            feature = slug
            feature_dir = lifecycle_base / slug
            dir_exists = True

    if mode == "resume" and not dir_exists:
        return {
            "state": "no-such-lifecycle",
            "feature": feature,
            "next": (
                f"No cortex/lifecycle/{feature}/ to resume. Report and stop; do not "
                "create it (that is bare-<feature> behavior)."
            ),
        }

    if not dir_exists:
        return {
            "state": "new",
            "feature": feature,
            "backlog": backlog,
            "phase": phase_override or "research",
            "next": "New feature — start the /cortex-core:refine flow at research.",
        }

    det = resolve_lifecycle_phase(feature_dir)
    route = phase_override or det["route"]
    out = {
        "state": "resume",
        "feature": feature,
        "backlog": backlog,
        "route": route,
        "phase": det["phase"],
        "paused": det["paused"],
        "checked": det["checked"],
        "total": det["total"],
        "cycle": det["cycle"],
        "criticality": read_criticality(feature, lifecycle_base),
        "tier": read_tier(feature, lifecycle_base),
        "staleness": lifecycle_staleness(feature_dir),
        "phase_override": bool(phase_override),
        "next": _next_for_route(route, bool(phase_override)),
    }
    if resolved_from is not None:
        # Evidence trail: the invocation token that remapped onto the slug.
        out["resolved_from"] = resolved_from
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-resolve",
        description=(
            "Resolve a /cortex-core:lifecycle invocation string to a single "
            "{state, next, ...} action struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "arguments",
        nargs="?",
        default="",
        help="The raw $ARGUMENTS string (a single quoted argument).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-resolve")
    args = _build_parser().parse_args(argv)
    result = resolve_invocation(args.arguments or "")
    result["protocol"] = PROTOCOL_VERSION
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
