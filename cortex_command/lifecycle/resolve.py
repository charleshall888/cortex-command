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

Identity (#379): a lifecycle's identity is the backlog item's canonical
``lifecycle_slug``; a ticket number, uuid prefix, filename stem, or title
phrase is input normalization — accepted here, stored nowhere. Every state
including ``new`` emits the canonical slug, with ``resolved_from`` carrying the
raw token as an evidence trail.

Accepted consequence — first-entry identity is provisional until ``enter``
pins it. When an item has no ``lifecycle_slug`` in frontmatter, the slug is
derived from its title, so editing the title between this resolve and the
``enter`` that writes ``index.md`` would derive a different slug. The window is
one skill turn: ``enter`` pins the slug at Step 2 before ``refine`` re-resolves
at Step 3, and frontmatter is priority-1 thereafter (``resolve_item.py:135``).
Not solved; the drift is bounded and self-closing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.generate_index import _is_deferred
from cortex_command.backlog.resolve_item import (
    _backlog_dir,
    _build_json,
    _item_title,
    _parse_frontmatter,
    resolve,
)
from cortex_command.common import (
    TERMINAL_STATUSES,
    lifecycle_staleness,
    normalize_status_spelling,
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
    "closed",
    "parked",
    "resume",
)

# Recorded-outcome routing (#480). Deliberately NOT folded into the `wontfix`
# state above: that one is the *invocation mode* (`/cortex-core:lifecycle
# wontfix <slug>`), an instruction to go close something. These two are a
# report about an item that is already closed or parked, so conflating them
# would change what the existing arm means.
#
# `closed` interpolates the status because the status IS the reason. `parked`
# does not: parking has two sanctioned spellings (the `deferred` tag and
# `status: deferred`), so naming one of them would misreport the other.
_OUTCOME_NEXT = {
    "closed": (
        "Backlog item is `status: {status}` — already finished. Report that and stop; "
        "do not start a lifecycle. Route only if the user explicitly asks to reopen it."
    ),
    "parked": (
        "Backlog item is parked — deliberately held, and NOT finished. Surface its "
        "recorded decision and revisit trigger, ask whether to unpark, and route only "
        "on a yes."
    ),
}


def _recorded_outcome(fm: dict) -> Optional[str]:
    """Classify a backlog item's recorded outcome: ``closed``, ``parked``, or neither.

    Terminal beats parked: an item that was parked and later finished is
    finished, so the terminal test runs first.

    ``_is_deferred`` is imported rather than re-spelled here. A second copy of
    the parking set is precisely the drift #456 exists because of — and it
    already recognizes both sanctioned spellings, which a reader holding only
    ``status`` cannot reconstruct.
    """
    if normalize_status_spelling(fm.get("status")) in TERMINAL_STATUSES:
        return "closed"
    # This resolver must never crash (it is exit-0 by contract), and frontmatter
    # is unvalidated on write — so coerce rather than trust. `tags: null` yields
    # None, and a non-str tag would blow up the predicate's `.strip()`.
    raw_tags = fm.get("tags")
    tags = [t for t in raw_tags if isinstance(t, str)] if isinstance(raw_tags, list) else []
    if _is_deferred({"status": fm.get("status") or "", "tags": tags}):
        return "parked"
    return None


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

# Discriminated-PHASE keys, deliberately separate from ``_ROUTE_NEXT``: these are
# not machine states, so they must never enter a route-keyed table (the transition
# table pins every ``_ROUTE_NEXT`` key as a real state). The rework cap's route
# stays the bare ``escalated``; only ``phase`` carries the discriminant, which
# ``_next_for_route`` matches by prefix so the cap is not narrated as a rejection.
_PHASE_NEXT = {
    "escalated:rework-cap": (
        "The rework cap was reached without a reviewer rejection — present the "
        "review findings and ask the user for direction. The recorded way to "
        "authorize another pass is the sanctioned override: cortex-lifecycle-event "
        "log --event <name> --feature <slug> (the sanctioned out-of-band hand-append)."
    ),
}


def _next_for_route(route: str, phase_overridden: bool, phase: Optional[str] = None) -> str:
    # The cap discriminant rides ``phase`` only; ``route`` stays ``escalated``.
    # An explicit --phase override decouples route from the detected phase, so
    # the discriminant is only trusted when there is no override.
    if (
        not phase_overridden
        and route == "escalated"
        and phase is not None
        and phase.startswith("escalated:rework-cap:")
    ):
        base = _PHASE_NEXT["escalated:rework-cap"]
    else:
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
        fm = _parse_frontmatter(res.item)
        out = _build_json(res.item, fm)
        # The recorded outcome is attached HERE, on this resolver's own copy,
        # rather than inside `_build_json`. Those four keys are a closed set
        # pinned by tests/test_resolve_backlog_item.py — the
        # `cortex-resolve-backlog-item` stdout contract — so widening them to
        # carry `status` would change a CLI this fix has no business touching.
        #
        # Both fields ride every state, not just the two that route on them:
        # on the `resume` arm the events log stays authoritative, but a reader
        # can now see that the ticket underneath it is closed or parked.
        out["status"] = normalize_status_spelling(fm.get("status"))
        out["outcome"] = _recorded_outcome(fm)
        return out
    if res.status == "ambiguous":
        return {
            "ambiguous": [
                {"filename": p.name, "title": _item_title(p, _parse_frontmatter(p))}
                for p in res.candidates[:5]
            ]
        }
    return None


def resolve_invocation(arguments: str, project_root: Optional[Path] = None) -> dict:
    """Classify + resolve a raw ``$ARGUMENTS`` string into one action struct.

    Trailing tokens the grammar dropped (#402) ride the struct as
    ``ignored_tokens`` — evidence the caller may surface, never a route.
    """
    parsed = parse(arguments)
    out = _resolve_parsed(parsed, arguments, project_root)
    if parsed.get("ignored_tokens"):
        out.setdefault("ignored_tokens", parsed["ignored_tokens"])
    return out


def _resolve_parsed(
    parsed: dict, arguments: str, project_root: Optional[Path] = None
) -> dict:
    """Resolve an already-classified ``parse()`` struct to the action struct."""
    root = project_root or Path.cwd()
    lifecycle_base = root / "cortex" / "lifecycle"
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
    canonical_slug = None
    if not dir_exists and isinstance(backlog, dict):
        slug = backlog.get("lifecycle_slug")
        # Defensive reader coercion (#378 req-3): a numeric lifecycle_slug read
        # as int must not reach the `lifecycle_base / slug` path-join below
        # (Path / int raises TypeError). Coerce a non-None value to str; the
        # None sentinel stays None (falsy, so the guard skips the remap).
        if slug is not None:
            slug = str(slug)
        if slug and slug != feature:
            canonical_slug = slug
            if (lifecycle_base / slug).is_dir():
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
        # #379 R8: a first entry keyed by ticket number (or any alias) is still
        # the backlog item's lifecycle, so the envelope names it by its
        # canonical slug — the same rule the resume arm above already applies,
        # minus the is_dir() conjunct that arm needs and this one cannot have
        # (there is no dir yet; that is what makes this state `new`). The state
        # itself is untouched: #370's edge — a backlog ID with no dir under its
        # slug still resolves `new` — is preserved (R9).
        if canonical_slug is not None:
            resolved_from = feature
            feature = canonical_slug

        # #480: the item's recorded outcome, before the `new` verdict below.
        #
        # Absence of a lifecycle directory was the ONLY evidence this arm read,
        # so a finished or parked ticket whose directory was never created — or
        # was archived as closure hygiene — came back as "New feature". Keying
        # on the status rather than on the directory is what makes archiving
        # unable to defeat the check: `cortex/lifecycle/archive/<slug>` never
        # has to be consulted, because the answer was never in the filesystem.
        #
        # Scoped to this arm on purpose. Where a live directory exists the
        # events log is authoritative and already routes correctly (measured:
        # every live-directory row in #480's table was right), and overriding it
        # from frontmatter would change the event-driven arm's meaning.
        outcome = backlog.get("outcome") if isinstance(backlog, dict) else None
        if outcome is not None:
            out = {
                "state": outcome,
                "feature": feature,
                "backlog": backlog,
                "next": _OUTCOME_NEXT[outcome].format(
                    status=backlog.get("status") or "unknown"
                ),
            }
            if resolved_from is not None:
                out["resolved_from"] = resolved_from
            return out

        out = {
            "state": "new",
            "feature": feature,
            "backlog": backlog,
            "phase": phase_override or "research",
            "next": "New feature — start the /cortex-core:refine flow at research.",
        }
        if resolved_from is not None:
            # Evidence trail: the invocation token that remapped onto the slug.
            out["resolved_from"] = resolved_from
        return out

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
        "next": _next_for_route(route, bool(phase_override), det["phase"]),
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
