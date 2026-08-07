"""cortex-lifecycle-review-brief — emit the reviewer brief for a review dispatch.

``cortex-lifecycle-review-brief --feature {slug}`` is the single source of the
reviewer brief for both consumers of the review phase: the interactive prose in
``skills/build/references/review.md`` (which calls this CLI) and the overnight
pipeline (which imports :func:`build_rework_brief` in-process). The prose keeps
only control flow and the call; the *narrative* output-shape prescription —
stage definitions, the ``## Requirements Drift`` and
``## Suggested Requirements Update`` formats, the verdict field-name
prohibitions — lives here. See ADR-0035.

Layering
--------

A **pure builder layer** with no I/O — :func:`build_full_brief`,
:func:`build_rework_brief`, :func:`parse_verdict_block`,
:func:`parse_carried_forward`, :func:`decide_test_baseline` — sits beneath a
**CLI/IO layer** (:func:`main` and its ``_``-prefixed helpers) that archives the
prior cycle, captures the dispatch baseline, and fails open. Both consumers call
*inward*: ``cortex_command/pipeline/review_dispatch.py`` imports this module,
never the reverse. That direction is load-bearing — ``review_dispatch`` pulls
the Claude Agent SDK, an optional extra, so the fenced-JSON verdict extraction
its ``parse_verdict`` performs is reimplemented here rather than imported.

What one invocation does
------------------------

1. Derives the dispatch cycle from ``count_rework_cycles`` (the existing
   counter, not ``common.py``'s reduced ``cycle``): ``N = rework_cycles + 1``,
   and mode is ``rework`` iff ``rework_cycles >= 1``.
2. **Archives** the prior cycle: ``review.md`` is *copied* (never moved) to
   ``review-cycle-{N-1}.md``, a no-op when that target already exists. Copy
   semantics plus no-clobber makes a retry after a crash converge without
   distinguishing "archive already taken" from "cycle-N write never completed".
   ``review.md`` must exist continuously — ``common.py``'s phase detection falls
   through to the plan-based step when it is missing and reports ``review``
   instead of ``implement-rework``.
3. **Records the dispatch baseline** as an additive ``review_dispatched``
   events.log row (``cycle``, ``mode``, ``baseline_sha``) via the shared
   ``lifecycle_event`` writer, idempotently: an existing row for the same cycle
   suppresses the append. events.log carries no SHA and no existing event fires
   at review dispatch, so this row is what gives requirements 7, 11 and 13 one
   mechanism. The rework baseline is the ``baseline_sha`` of the ``cycle N-1``
   row. ``mode`` is the mode actually **served**, so a rework that degrades to a
   full brief records ``full``; a ``full`` row at cycle >= 2 is therefore exactly
   a degraded rework.
4. Emits the brief on stdout.

Fail-open contract
------------------

Exit **0** — the brief was served. Exit **3** — *degraded*: a **full** brief is
still written to stdout and a ``DEGRADED: <reason>`` line to stderr. The verb
degrades (and never emits a scoped brief) when the archive is missing or
unreadable, its verdict block is unparseable, its ``issues`` array is empty, or
no prior ``review_dispatched`` row supplies a baseline SHA. An empty checklist
is never emitted as a scoped brief: ``parse_verdict``'s failure sentinel is
``{"verdict": "ERROR", "cycle": 0, "issues": []}``, so downstream an empty
``issues`` array and a read failure are indistinguishable, and a reviewer handed
one has no signal to widen its reading. Exit **1** only when the project root
cannot be resolved — nothing is written to stdout, and the caller's own
"non-zero exit or no output" rule takes over.

``PROTOCOL_VERSION`` is deliberately not bumped by this verb's introduction: no
served payload shape changed, and the fail-open contract wants a stale wheel to
degrade rather than halt. The brief's *shape* is nonetheless protocol-governed —
a later shape change the prose depends on moves the floor. See
``cortex_command/lifecycle/protocol.py``.

Structure mirrors ``stage_artifacts.py``: pure helpers plus a thin
``main(argv) -> int``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)
from cortex_command.lifecycle.counters import count_rework_cycles
from cortex_command.lifecycle_event import log_event_at

_GIT_TIMEOUT = 10

_EVENT_NAME = "review_dispatched"

# The two decision tokens requirement 11 allows. Exactly one reaches the brief,
# and neither token may appear anywhere in the other's explanatory prose — the
# acceptance criterion greps for "exactly one of".
REUSE_BASELINE = "reuse baseline"
RE_RUN = "re-run"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Same fenced-JSON extraction ``review_dispatch.parse_verdict`` performs:
# the *first* ```json fence in the file. Matching it exactly is deliberate —
# it makes this verb degrade in precisely the cases where the pipeline's own
# parse would return its ERROR sentinel, rather than in a different set.
_VERDICT_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

_REQUIREMENT_HEADING = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
_CARRIED_FORWARD_MARKER = "carried forward from cycle"


# ---------------------------------------------------------------------------
# Pure builder layer — no I/O
# ---------------------------------------------------------------------------


def parse_verdict_block(text: str) -> Optional[dict]:
    """Extract the Verdict JSON object from a review artifact's *text*.

    Performs the same fenced-JSON extraction ``parse_verdict`` performs in
    ``cortex_command/pipeline/review_dispatch.py`` — the first ```` ```json ````
    fence containing an object — reimplemented rather than imported because that
    module pulls the Claude Agent SDK, an optional extra.

    Returns the parsed dict, or ``None`` when no fence is present, the fence
    does not parse, or it parses to something other than an object. ``None`` is
    a *degrade* signal to the caller; it never becomes an empty checklist.
    """
    match = _VERDICT_FENCE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_carried_forward(text: str) -> list[str]:
    """Return the requirement headings *text* already carried forward.

    Scans a prior cycle's review artifact for ``### Requirement:`` headings
    whose block carries a rating line matching ``carried forward from cycle``.
    A rating may be carried **once**, so every heading returned here is one the
    next cycle must re-verify rather than carry again — without that bound a
    cycle-3 review can carry a cycle-2 carry-forward of a cycle-1 rating and the
    line item is never re-read by anyone.

    Headings are returned in document order, at most once each.
    """
    found: list[str] = []
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        heading = _REQUIREMENT_HEADING.match(line)
        if heading:
            current = heading.group(1)
            continue
        if line.startswith("#"):
            # Any other heading closes the requirement block.
            current = None
            continue
        if current and _CARRIED_FORWARD_MARKER in line.lower():
            found.append(current)
            current = None
    return found


def decide_test_baseline(changed_paths: Iterable[str], feature: str) -> str:
    """Decide whether the handed test baseline still describes HEAD.

    Returns :data:`RE_RUN` iff *changed_paths* (the repo-relative
    ``git diff <baseline>..HEAD --name-only`` set) reports any path other than
    ``cortex/lifecycle/{feature}/*.md``; otherwise :data:`REUSE_BASELINE`.

    The exemption is deliberately narrow, and **``events.log`` is not exempt**:
    ``tests/test_clarify_critic_alignment_integration.py``'s
    ``test_post_migration_clarify_critic_events_are_jsonl`` walks the real
    ``cortex/lifecycle/*/events.log`` tree and asserts format compliance, so a
    rework confined to a lifecycle directory can still turn a live test red.
    Nested paths under the feature directory (``captures/`` evidence) are not
    exempt either — only the flat ``*.md`` artifacts are.

    An empty diff reuses: nothing changed, so nothing can have broken.
    """
    prefix = f"cortex/lifecycle/{feature}/"
    for raw in changed_paths:
        path = raw.strip()
        if not path:
            continue
        if (
            path.startswith(prefix)
            and path.endswith(".md")
            and "/" not in path[len(prefix):]
        ):
            continue
        return RE_RUN
    return REUSE_BASELINE


def _output_shape_section(review_path: str) -> str:
    """The output-shape prescription both modes carry.

    This is the narrative that used to live in ``review.md`` §2 — moved here so
    the always-read prose keeps only control flow. The Verdict JSON *block*
    itself deliberately stays in that prose: it is the contract ``parse_verdict``
    depends on and must not be reachable only through a subprocess.
    """
    return f"""## Output shape

Write your review to `{review_path}`. It carries a `## Requirements Drift` section with three fields:

- **State**: `none` | `detected`
- **Findings**: one bullet per drifted item, or "None"
- **Update needed**: a requirements file path, or "None"

Requirements drift is an *observation* that does not affect the verdict: `none` when the implementation
matches the requirements and adds no unreflected behavior, `detected` when it introduces or changes behavior
they do not capture. When you are uncertain, log `detected` — a false positive auto-applies a small update, a
false negative silently hides drift.

On `detected`, add a `## Suggested Requirements Update` section, one entry per drifted file, each naming:

- **File**: the requirements file path
- **Section**: an existing heading in that file
- **Content**: the exact 1–3 lines to append, written as they should appear rather than described.

End the file with the Verdict JSON block in the fenced form the review phase's contract prescribes, using
exactly the field names `verdict`, `cycle`, `issues` and `requirements_drift` — not "overall" / "result" /
"status", and not the Stage-1 PASS/FAIL values in `verdict`, whose vocabulary is
APPROVED / CHANGES_REQUESTED / REJECTED. Downstream processing depends only on that block."""


def _preamble(feature: str, cycle: int, mode: str, review_path: str) -> str:
    return f"""# Reviewer brief — {feature} · cycle {cycle} · {mode}

You are a read-only reviewer. You modify no file except `{review_path}`, which you write. You consume the
test baseline the orchestrator handed you — a pass/fail summary and a log path — and never re-execute the
suite yourself. Any sub-agent you spawn is read-only and returns its findings as a message envelope."""


def build_full_brief(
    *,
    feature: str,
    cycle: int,
    review_path: str,
    degraded_reason: Optional[str] = None,
) -> str:
    """Build the full (unscoped) reviewer brief.

    Args:
        feature: Feature slug.
        cycle: The dispatch cycle number (``rework_cycles + 1``).
        review_path: **Absolute** path of ``cortex/lifecycle/{feature}/review.md``.
        degraded_reason: When set, the brief opens by naming why a scoped brief
            could not be built. The reviewer is told the read failure rather
            than handed a silently-empty checklist.
    """
    parts = [_preamble(feature, cycle, "full review", review_path)]

    if degraded_reason:
        parts.append(
            "**Degraded dispatch.** The prior cycle's issues could not be read, so this review is "
            f"unscoped: {degraded_reason}. Review the full specification as described below, and report "
            "the degradation in your review — the read failure is not evidence that the prior cycle "
            "found nothing."
        )

    parts.append(
        """## Scope

Two-stage review.

**Stage 1 — spec compliance.** Per requirement, read the relevant source, check the acceptance criteria, and
rate PASS / FAIL / PARTIAL. Any FAIL skips Stage 2. Stage 1 runs at complex tier, or at any tier once
criticality is `high` / `critical`.

**Stage 2 — code quality** (only when Stage 1 produced no FAIL; complex tier only). Naming consistency, error
handling, whether the plan's verification steps were actually executed, and pattern consistency with the
surrounding code.

Flag minor code-quality issues as PARTIAL with notes rather than failing the requirement outright."""
    )

    parts.append(_output_shape_section(review_path))
    return "\n\n".join(parts) + "\n"


def build_rework_brief(
    *,
    feature: str,
    cycle: int,
    issues: list[str],
    baseline_sha: str,
    review_path: str,
    baseline_decision: str,
    carried_forward: Optional[list[str]] = None,
) -> str:
    """Build the rework-scoped reviewer brief.

    Args:
        feature: Feature slug.
        cycle: The dispatch cycle number; the checklist comes from ``cycle - 1``.
        issues: The prior cycle's issue texts. Must be non-empty — an empty
            checklist is never emitted as a scoped brief (the caller degrades to
            :func:`build_full_brief` instead).
        baseline_sha: The 40-hex SHA recorded at the prior cycle's dispatch. It
            opens the reading range ``{baseline_sha}..HEAD``.
        review_path: **Absolute** path of ``cortex/lifecycle/{feature}/review.md``.
        baseline_decision: :data:`REUSE_BASELINE` or :data:`RE_RUN`, normally
            from :func:`decide_test_baseline`. Required rather than defaulted so
            an in-process caller (the overnight pipeline, which runs its own
            suite in a worktree) states its choice instead of inheriting one.
        carried_forward: Requirement headings the prior cycle already carried
            forward, from :func:`parse_carried_forward`. They may not be carried
            again and are listed as requiring re-verification.

    Raises:
        ValueError: When *issues* is empty.
    """
    if not issues:
        raise ValueError(
            "build_rework_brief requires a non-empty checklist; "
            "an empty checklist must degrade to a full brief"
        )

    prior = cycle - 1
    parts = [_preamble(feature, cycle, "rework re-review (scoped)", review_path)]

    parts.append(
        f"""## Reading scope

Cycle {prior} returned CHANGES_REQUESTED and the flagged work has since been reworked. Your question is
narrower than a first-pass review: did the flagged issues close, and did any fix break something. Read the
commit range `{baseline_sha}..HEAD` — that is the whole of the rework — plus whatever the checklist below
sends you to.

**Scoping bounds your reading, never your concluding.** The range tells you what you are guaranteed to have
read; it does not license passing over a genuine problem you can see from there. If the rework introduced or
exposed something outside the checklist, report it."""
    )

    checklist = "\n".join(f"{i}. {text}" for i, text in enumerate(issues, start=1))
    parts.append(
        f"""## Prior-Cycle Checklist

Your review must contain a `## Prior-Cycle Checklist` section giving **one explicit disposition per item
below** — resolved / not resolved / partially resolved, each with the evidence you saw. No item may be
dropped silently, and an item you find resolved must not be re-emitted under the new-problems section: a
re-review that re-reports what the rework already fixed is duplicate-suggestion spam, not a finding.

Issues raised in cycle {prior}:

{checklist}"""
    )

    parts.append(
        """## Out-of-Scope Findings

Your review must contain a `## Out-of-Scope Findings` heading, and it must be filled **affirmatively even
when empty** — "None found outside the checklist" — never omitted. An omitted section is indistinguishable
from a section nobody looked for, which is exactly what makes a scoped review a rubber stamp."""
    )

    if baseline_decision == REUSE_BASELINE:
        baseline_body = (
            f"The commit range touches only `cortex/lifecycle/{feature}/*.md`, so the baseline the "
            "orchestrator handed you still describes HEAD. Consume it as given; do not execute the suite."
        )
    else:
        baseline_body = (
            f"The commit range touches paths outside `cortex/lifecycle/{feature}/*.md`, so the orchestrator "
            "refreshes the test baseline before you consume it. Consume the refreshed summary and log path; "
            "do not execute the suite yourself."
        )
    parts.append(
        f"""## Test baseline

Decision: **{baseline_decision}**

{baseline_body}"""
    )

    carry_parts = [
        f"""## Carry-forward

A requirement rated in the immediately preceding cycle and untouched by this rework may be reported as
carried forward rather than silently re-asserted as a fresh rating. State it **by reference, naming the cycle
and the condition** under which the rating still holds — for example:
`PASS — carried forward from cycle {prior}; holds while the loader's path list is unchanged`.

A rating may be carried forward **once**. A requirement whose rating would be carried a second consecutive
time must be re-verified instead. Carry-forward is a default that saves reading, never a constraint on your
conclusions: re-open and re-rate anything you disagree with."""
    ]
    if carried_forward:
        listed = "\n".join(f"- {name}" for name in carried_forward)
        carry_parts.append(
            f"""Cycle {prior} already carried these forward, so they have exhausted the bound and
**require re-verification** this cycle — they may not be carried again:

{listed}"""
        )
    parts.append("\n\n".join(carry_parts))

    parts.append(_output_shape_section(review_path))
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# CLI/IO layer
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> Optional[str]:
    """Run ``git <args>`` in *cwd*; return stripped stdout, or None on failure."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _read_events(events_log: Path) -> list[dict]:
    """Return the parsed event dicts from *events_log* (tolerant, in order).

    Non-JSON and malformed lines are skipped rather than raised on — the
    events.log tolerant-reader convention shared with ``counters.py`` and
    ``common.py``.
    """
    if not events_log.is_file():
        return []
    try:
        content = events_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _as_int(value: object) -> Optional[int]:
    """Coerce an events.log field to int, or None. Tolerates a string form."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _dispatch_row_for_cycle(rows: list[dict], cycle: int) -> Optional[dict]:
    """The last ``review_dispatched`` row whose ``cycle`` equals *cycle*.

    Cycle-qualified presence, matching the check ``advance.py`` uses: a row for
    *this* cycle suppresses a duplicate append on replay, while a row for an
    earlier cycle does not.
    """
    match: Optional[dict] = None
    for row in rows:
        if row.get("event") != _EVENT_NAME:
            continue
        if _as_int(row.get("cycle")) == cycle:
            match = row
    return match


def _baseline_from_row(row: Optional[dict]) -> Optional[str]:
    """The row's ``baseline_sha`` when it is a well-formed 40-hex SHA."""
    if not row:
        return None
    sha = row.get("baseline_sha")
    if isinstance(sha, str) and _SHA_RE.match(sha.strip()):
        return sha.strip()
    return None


def _archive_prior_cycle(feature_dir: Path, cycle: int) -> None:
    """Copy ``review.md`` to ``review-cycle-{cycle-1}.md``.

    Copy, **never** move: a window in which ``review.md`` is absent makes phase
    detection fall through to the plan-based step and report ``review`` instead
    of ``implement-rework``. A no-op when the target already exists, which is
    what makes a retry after a crash converge — at any point, including after a
    partial cycle-N write — without having to distinguish "archive already
    taken" from "cycle-N write never completed".

    Silent no-op at cycle 1: there is no prior cycle to archive. Any I/O failure
    is swallowed; the caller's own degrade path reports the resulting missing
    archive rather than this step raising.
    """
    if cycle < 2:
        return
    source = feature_dir / "review.md"
    target = feature_dir / f"review-cycle-{cycle - 1}.md"
    if not source.is_file() or target.exists():
        return
    try:
        shutil.copy2(source, target)
    except OSError:
        return


def _record_baseline(
    events_log: Path,
    rows: list[dict],
    feature: str,
    cycle: int,
    mode: str,
    root: Path,
) -> None:
    """Record this dispatch's baseline SHA as an additive events.log row.

    Idempotent on the cycle: an existing ``review_dispatched`` row for *cycle*
    suppresses the append, so a re-dispatch of the same cycle keeps the original
    baseline rather than sliding it forward onto the rework's own commits.
    Skipped entirely when HEAD cannot be resolved — a lifecycle outside a git
    repo still gets its brief, it just cannot offer a range next cycle.
    """
    if _dispatch_row_for_cycle(rows, cycle) is not None:
        return
    head = _git(["rev-parse", "HEAD"], root)
    if not head or not _SHA_RE.match(head):
        return
    log_event_at(
        events_log,
        {
            "event": _EVENT_NAME,
            "feature": feature,
            "cycle": cycle,
            "mode": mode,
            "baseline_sha": head,
        },
    )


def _changed_paths(baseline_sha: str, root: Path) -> Optional[list[str]]:
    """``git diff <baseline_sha>..HEAD --name-only`` as repo-relative paths.

    Two-dot ``..`` is correct and not the three-dot trap: the baseline is always
    an ancestor of HEAD on a rework, so ``..`` and ``...`` are equivalent and
    ``..`` says what is meant. Returns None when the diff cannot be taken.
    """
    out = _git(["diff", f"{baseline_sha}..HEAD", "--name-only"], root)
    if out is None:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-review-brief",
        description=(
            "Emit the reviewer brief for a review dispatch on stdout, "
            "selecting full or rework-scoped mode from the feature's rework "
            "count. Archives the prior cycle's review.md and records the "
            "dispatch baseline SHA. Exit 0 = brief served; exit 3 = degraded "
            "(a full brief is still served, with the reason on stderr)."
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug under cortex/lifecycle/ (e.g., my-feature-name).",
    )
    parser.add_argument(
        "--lifecycle-dir",
        default="cortex/lifecycle",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for cortex-lifecycle-review-brief."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        root = _resolve_user_project_root_from_cwd()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-review-brief: {exc}\n")
        return 1

    feature = args.feature
    lifecycle_base = Path(args.lifecycle_dir)
    if not lifecycle_base.is_absolute():
        lifecycle_base = root / lifecycle_base
    feature_dir = lifecycle_base / feature
    events_log = feature_dir / "events.log"
    review_path = str((feature_dir / "review.md").resolve())

    rework_cycles = count_rework_cycles(events_log)
    cycle = rework_cycles + 1
    mode = "rework" if rework_cycles >= 1 else "full"

    # Archive first: the copy must be on disk before anything can write cycle N
    # over review.md, and it is the scoped checklist's only interactive source.
    _archive_prior_cycle(feature_dir, cycle)

    rows = _read_events(events_log)

    def _record(served_mode: str) -> None:
        """Record the dispatch with the mode actually *served*, not the mode the
        rework counter selected. A degraded rework serves a full brief and so
        records ``full``; since ``mode`` is ``rework`` for exactly the cycles
        ``>= 2``, a ``full`` row at cycle >= 2 is precisely a degraded rework,
        which keeps the field a two-value enum matching ``lifecycle_event``'s
        ``review-dispatched`` subcommand while still answering "did any rework
        silently degrade?" from events.log alone.
        """
        _record_baseline(events_log, rows, feature, cycle, served_mode, root)

    def _degrade(reason: str) -> int:
        _record("full")
        sys.stdout.write(
            build_full_brief(
                feature=feature,
                cycle=cycle,
                review_path=review_path,
                degraded_reason=reason,
            )
        )
        sys.stderr.write(f"DEGRADED: {reason}\n")
        return 3

    if mode == "full":
        _record("full")
        sys.stdout.write(
            build_full_brief(feature=feature, cycle=cycle, review_path=review_path)
        )
        return 0

    archive_path = feature_dir / f"review-cycle-{cycle - 1}.md"
    try:
        archive_text = archive_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return _degrade(
            f"cycle {cycle - 1} archive is missing or unreadable at {archive_path}"
        )

    verdict = parse_verdict_block(archive_text)
    if verdict is None:
        return _degrade(
            f"cycle {cycle - 1} archive at {archive_path} carries no parseable "
            "Verdict JSON block"
        )

    raw_issues = verdict.get("issues")
    issues = (
        [str(item) for item in raw_issues if str(item).strip()]
        if isinstance(raw_issues, list)
        else []
    )
    if not issues:
        return _degrade(
            f"cycle {cycle - 1} verdict carries an empty issues array, which is "
            "indistinguishable from a failed parse — refusing to emit an empty checklist"
        )

    baseline_sha = _baseline_from_row(_dispatch_row_for_cycle(rows, cycle - 1))
    if baseline_sha is None:
        return _degrade(
            f"no review_dispatched row for cycle {cycle - 1} supplies a baseline SHA"
        )

    changed = _changed_paths(baseline_sha, root)
    # An untakeable diff decides toward safety: the reviewer gets a refreshed
    # baseline rather than a stale one asserted as current.
    decision = (
        RE_RUN if changed is None else decide_test_baseline(changed, feature)
    )

    _record("rework")
    sys.stdout.write(
        build_rework_brief(
            feature=feature,
            cycle=cycle,
            issues=issues,
            baseline_sha=baseline_sha,
            review_path=review_path,
            baseline_decision=decision,
            carried_forward=parse_carried_forward(archive_text),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
