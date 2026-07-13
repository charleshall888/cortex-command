"""cortex-lifecycle-advance — the write-side executor of the served lifecycle loop.

``advance`` is the ONLY sanctioned way the served loop (``next`` reads, ``advance``
writes) moves a feature's lifecycle state. It composes the four B1 verb decision
cores' fixed-source-order emission bodies inside ONE gate-checked body, wrapped in
Task 6's claim/commit locking primitive so a transition is atomic under contention
(``cortex_command.lifecycle_event.claim_transition`` / ``commit_transition``).

Why advance re-emits the legacy vocabulary rather than calling the B1 cores
verbatim (the crux of the design): the B1 verbs emit their legacy vocabulary
(``phase_transition``/``plan_approved``/…) through ``log_event`` WITHOUT an
``invocation_id``. Those event names are in the primitive's ``_STATE_MOVING_EVENTS``
interleave set, so if advance let an unmodified B1 core emit them BETWEEN its claim
and commit, commit's re-reduce would see them as FOREIGN state-moving rows and
refuse with "state moved since claim". advance therefore emits the same legacy rows
itself, threading the deterministic ``invocation_id`` as an additive field, so
commit recognises them as this invocation's own rows (``r["invocation_id"] ==
invocation_id`` → skipped). This is exactly what the transition table's
``Transition.emits`` was authored to reference ("the reference for advance's
dual-emission") and what the events-registry records as the advance-authored
``invocation_id`` field on the legacy-vocabulary rows. The B1 cores remain the
authority for the ROUTING rules (``review_verdict._route_target`` /
``implement_transition._resolve_route`` are imported, not re-derived) and for the
non-advance typed-subcommand emission path.

Dual-emission:
  * PRIMARY — the exact legacy event vocabulary (``plan_approved`` /
    ``phase_transition`` / ``review_verdict`` / ``spec_approved`` /
    ``drift_protocol_breach`` / ``feature_paused`` / ``lifecycle_cancelled`` /
    ``batch_dispatch``), canonically serialized (``json.dumps(row)+"\\n"``, default
    spacing) so legacy readers (``common.detect_lifecycle_phase`` /
    ``reduce_lifecycle_state``) parse them unchanged; each carries the additive,
    optional ``invocation_id`` so an advance-authored row is distinguishable from an
    independent legacy emission during the dual-emission window.
  * ADDITIVE MACHINE ROWS — the ``advance_started`` / ``advance_committed`` pair the
    claim/commit primitive appends, both carrying the same ``invocation_id``.

Per-side-effect existence probes make the whole verb idempotent: a crash between
claim and side effects, or between two side effects, is repaired by re-invoking the
SAME logical advance (same business tuple → same ``invocation_id`` via
``derive_invocation_id``); claim resumes the orphaned ``advance_started`` and each
legacy emission is skipped when already present (parsed-field match, never a
substring).

Refusals name BOTH the missing evidence AND the sanctioned override: the documented
out-of-band hand-append is ``cortex-lifecycle-event log`` (operator req 7). advance
refuses on an in-flight claim, a from-state gate mismatch, a commit-time interleave,
or an event-backed pause it may not cross.

Pause enforcement is SCOPED (R12 / hazard 10 / adversarial finding 10): advance
refuses to cross an EVENT-BACKED pause — an active ``feature_paused`` whose kind is
enforcement-bearing (``relayed-consent`` / ``phase-exit-wait``) and which this
invocation did not itself author — but NEVER refuses on a judgment/config-conditional
pause KIND (``config-conditional`` / ``question``); those are describe-only metadata
the wheel surfaces through ``next``/``describe``, never a runtime refusal.

House verb style: never-crash exit-0 ``{"state": ...}`` envelopes; ``_reject_unsafe_slug``
first (a feature slug composes into a filesystem path — the real injection surface);
``KNOWN_STATES`` is a closed tuple.

Extension seams (Tasks 14a / 14b bolt onto THIS file, serialized after this core):
  * :func:`_consent_cross_check` — Task 14b's pre-side-effect gh PR-state cross-check
    (hazard 5, fabricated-attestation defense). Runs OUTSIDE the flock (network never
    under lock — the claim/commit split exists for this) via an injectable subprocess
    seam (:func:`_run_gh`), so CI mocks the ``gh`` boundary with no network. A
    merge-consent transition (``review.approved`` — review→complete) whose feature
    carries a recorded PR (a ``pr_opened`` row) refuses when that PR is not actually
    merged. The companion quoted-utterance payload lands field-additively on the
    ``plan_approved``/``spec_approved`` rows (the additive ``consent_utterance`` field,
    threaded through :func:`_emission_plan`, NOT a new event).
  * :func:`_project_status` — Task 14a's post-commit monotonic status projection
    (cortex-backlog backend only, ADR-0016) with the archive-shadow guard. Core body
    is a no-op.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import _parse_frontmatter, resolve
from cortex_command.backlog.update_item import update_item
from cortex_command.common import (
    _resolve_user_project_root_from_cwd,
    detect_lifecycle_phase,
    normalize_status,
    reduce_lifecycle_state,
)
from cortex_command.lifecycle_config import resolve_backlog_backend
from cortex_command.lifecycle import review_verdict as rv
from cortex_command.lifecycle import implement_transition as it
from cortex_command.lifecycle import transition_table as tt
from cortex_command.lifecycle.log_resolver import resolve_events_log
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle_event import (
    claim_transition,
    commit_transition,
    derive_invocation_id,
    log_event_at,
)

_VERBS = ("plan-decision", "review-verdict", "spec-approve", "implement-transition")

# The four B1 decision cores this verb composes, by the owning_verb key their
# transition-table rows carry (transition_table.Transition.owning_verb).
_VERB_TO_OWNING = {
    "plan-decision": "plan_decision",
    "review-verdict": "review_verdict",
    "spec-approve": "spec_approve",
    "implement-transition": "implement_transition",
}

# Pause kinds advance structurally enforces (event-backed): an active feature_paused
# of one of these kinds blocks a crossing advance. The judgment/config-conditional
# kinds (``config-conditional`` / ``question``) are describe-only metadata and are
# deliberately absent — advance never refuses on them (R12 / hazard 10).
_ENFORCED_PAUSE_KINDS: frozenset[str] = frozenset({"relayed-consent", "phase-exit-wait"})

# The documented out-of-band hand-append every refusal points the operator at.
_SANCTIONED_OVERRIDE = (
    "cortex-lifecycle-event log --event <name> --feature <slug> [--set k=v ...] "
    "(the sanctioned out-of-band hand-append; see bin/.events-registry.md)"
)

# Merge-consent transitions (Task 14b / hazard 5): transition ids whose consent to
# advance rests on a real merged PR. ``review.approved`` (review→complete) consummates
# the feature — when a PR backs the work, that PR must ACTUALLY be merged, so a
# fabricated merge attestation cannot advance the feature to complete. The cross-check
# only fires when a ``pr_opened`` row records a PR; a trunk-mode completion carries no
# PR and is not cross-checked (there is nothing to verify, and requiring a PR would
# wrongly refuse the legitimate no-PR path). The check runs OUTSIDE the flock.
_MERGE_CONSENT_TRANSITION_IDS: frozenset[str] = frozenset({"review.approved"})

# The gh PR ``state`` values that count as a genuine merge (the consented state).
_MERGED_PR_STATES: frozenset[str] = frozenset({"MERGED"})

# Timeout for the gh cross-check subprocess (mirrors complete_route._GH_TIMEOUT).
_GH_TIMEOUT = 30

# The additive field the operator's verbatim consent utterance lands on for a human
# consent underlying a plan_approved/spec_approved transition (hazard 5, fabricated-
# attestation defense): the row carries the exact quoted text so a fabricated consent
# is a specific, falsifiable lie rather than a bare flag. Additive-only — emitted only
# when supplied; the legacy-vocabulary rows omit it otherwise.
_CONSENT_UTTERANCE_FIELD = "consent_utterance"
_CONSENT_UTTERANCE_EVENTS: frozenset[str] = frozenset({"plan_approved", "spec_approved"})

# Closed set of ``state`` values advance can emit (house style): the union of the
# four B1 cores' decision states (drift-proof — re-derived from the real modules)
# plus advance's own refusal state. ``error`` rides in from the B1 tuples.
from cortex_command.lifecycle import plan_decision as _pd  # noqa: E402
from cortex_command.lifecycle import spec_approve as _sa  # noqa: E402

KNOWN_STATES = tuple(
    sorted(
        set(_pd.KNOWN_STATES)
        | set(rv.KNOWN_STATES)
        | set(_sa.KNOWN_STATES)
        | set(it.KNOWN_STATES)
        | {"refused"}
    )
)


def _reject_unsafe_slug(feature: str) -> Optional[dict]:
    """Return an error envelope when *feature* is empty or carries a path
    separator / ``..`` — a path-traversal guard applied BEFORE any filesystem
    access. Returns None when the slug is safe to use as a directory component.
    """
    if not feature or "/" in feature or "\\" in feature or ".." in feature:
        return {
            "state": "error",
            "message": f"unsafe feature slug {feature!r}: no path separators or '..'",
        }
    return None


def _read_rows(log_path: Path) -> List[dict]:
    """Read *log_path* into an ordered list of parsed dict rows (tolerant).

    A missing file yields ``[]``; a torn line or non-dict JSON value is skipped,
    never raised — the same discipline the reducer and the primitive use.
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, OSError):
        return []
    rows: List[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _row_present(rows: List[dict], event: str, match_fields: dict) -> bool:
    """True when *rows* already carries a parsed ``event``-field match (plus every
    ``match_fields`` key/value) — never a substring. Mirrors the B1 cores'
    ``_event_exists`` so an advance-authored row idempotently suppresses a duplicate
    against either its own retry OR an independent legacy emission of the same row.
    """
    for r in rows:
        if r.get("event") != event:
            continue
        if match_fields and any(r.get(k) != v for k, v in match_fields.items()):
            continue
        return True
    return False


def _last_significant(rows: List[dict]) -> Optional[dict]:
    """Return the last state-significant row (the same four event kinds
    ``common._detect_lifecycle_phase_inner`` tracks for its ``paused`` bool), or
    None. A feature is actively paused iff this row's event is ``feature_paused``.
    """
    significant = ("phase_transition", "feature_complete", "feature_wontfix", "feature_paused")
    last: Optional[dict] = None
    for r in rows:
        if r.get("event") in significant:
            last = r
    return last


def _pause_refusal(rows: List[dict], invocation_id: str) -> Optional[dict]:
    """Return a refusal envelope when an EVENT-BACKED pause blocks a crossing advance.

    Refuses iff the last state-significant row is an active ``feature_paused`` whose
    kind is enforcement-bearing (:data:`_ENFORCED_PAUSE_KINDS`) AND which this
    invocation did not itself author (``invocation_id`` differs / is absent). A
    kind-absent legacy row fails closed to the most-restrictive kind, matching the
    reducer (``common.MOST_RESTRICTIVE_PAUSE_KIND``), so an under-specified pause is
    still enforced. Returns None for a describe-only kind (``config-conditional`` /
    ``question``) — those never refuse (R12 / hazard 10) — and None when this
    invocation authored the active pause (its own wait-approved retry).
    """
    last = _last_significant(rows)
    if last is None or last.get("event") != "feature_paused":
        return None
    if last.get("invocation_id") == invocation_id:
        return None  # this invocation's own pause (e.g. a wait-approved retry)
    kind = last.get("kind")
    if not (isinstance(kind, str) and kind in tt.PAUSE_KINDS):
        kind = "relayed-consent"  # fail closed, mirroring the reducer default
    if kind not in _ENFORCED_PAUSE_KINDS:
        return None  # judgment/config-conditional pause — describe-only, never refuse
    slug = last.get("slug", "<unslugged>")
    return {
        "state": "refused",
        "reason": (
            f"event-backed pause blocks advance: an active feature_paused "
            f"(slug={slug!r}, kind={kind!r}) is unresolved"
        ),
        "missing_evidence": (
            f"a resume/override clearing the active {kind!r} pause (slug={slug!r})"
        ),
        "sanctioned_override": _SANCTIONED_OVERRIDE,
        "pause": {"slug": slug, "kind": kind},
    }


# ---------------------------------------------------------------------------
# Emission plans — the fixed-source-order legacy vocabulary per composed arm
# ---------------------------------------------------------------------------
#
# Each plan is (transition_row, [emission, ...]) where an emission is
# {"event", "fields": [(key, value), ...], "match": {discriminating fields}}. The
# ``fields`` order and the ``match`` discriminants mirror the owning B1 core body
# exactly (plan_decision / review_verdict / spec_approve / implement_transition);
# advance appends the additive ``invocation_id`` after ``fields`` at emit time.


class _PlanError(Exception):
    """A malformed decision (bad arg / unknown arm) → an ``error`` envelope."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _emission_plan(
    *,
    verb: str,
    log_path: Path,
    decision: Optional[str],
    dispatch_choice: Optional[str],
    verdict: Optional[str],
    cycle: int,
    drift: Optional[str],
    breach: bool,
    retries: int,
    emit_transition: bool,
    batch: Optional[int],
    tasks: Optional[list],
    mode: Optional[str],
    consent_utterance: Optional[str] = None,
) -> tuple[tt.Transition, str, list[dict]]:
    """Resolve the composed arm to its table row, decision-state, and ordered
    legacy emissions. Reuses the B1 cores' pure routing helpers (never re-derived).
    Raises :class:`_PlanError` on a malformed decision.

    *consent_utterance* (Task 14b, hazard 5): when supplied, the operator's verbatim
    quoted consent text is appended field-additively (:data:`_CONSENT_UTTERANCE_FIELD`)
    to the ``plan_approved``/``spec_approved`` emissions ONLY — the fabricated-
    attestation defense. Absent (``None``), the field is omitted entirely, so the
    legacy rows keep their exact pre-14b shape.
    """
    owning = _VERB_TO_OWNING[verb]

    if verb == "plan-decision":
        if decision not in ("branch-mode-approved", "wait-approved", "cancelled", "revise"):
            raise _PlanError(f"plan-decision requires a valid --decision, got {decision!r}")
        decision_state = decision
        if decision == "branch-mode-approved":
            if dispatch_choice not in _pd._VALID_MODES:
                raise _PlanError(
                    f"branch-mode-approved requires --dispatch-choice ∈ {_pd._VALID_MODES}, "
                    f"got {dispatch_choice!r}"
                )
            emissions = [
                {"event": "plan_approved", "fields": [("dispatch_choice", dispatch_choice)], "match": {}},
                {"event": "phase_transition", "fields": [("from", "plan"), ("to", "implement")],
                 "match": {"from": "plan", "to": "implement"}},
            ]
        elif decision == "wait-approved":
            emissions = [
                {"event": "plan_approved", "fields": [("dispatch_choice", "wait")], "match": {}},
                {"event": "feature_paused",
                 "fields": [("slug", "plan-approval"), ("kind", "relayed-consent")], "match": {}},
            ]
        elif decision == "cancelled":
            emissions = [{"event": "lifecycle_cancelled", "fields": [], "match": {}}]
        else:  # revise — short-circuit, no emissions
            emissions = []

    elif verb == "review-verdict":
        if verdict not in rv._VERDICTS:
            raise _PlanError(f"review-verdict requires --verdict ∈ {rv._VERDICTS}, got {verdict!r}")
        if drift not in rv._DRIFT_VALUES:
            raise _PlanError(f"review-verdict requires --drift ∈ {rv._DRIFT_VALUES}, got {drift!r}")
        target = rv._route_target(verdict, cycle)  # reuse the B1 routing rule
        decision_state = rv._TARGET_TO_STATE[target]
        emissions = [
            {"event": "review_verdict",
             "fields": [("verdict", verdict), ("cycle", cycle), ("requirements_drift", drift)],
             "match": {"cycle": cycle}},
        ]
        if breach:
            emissions.append({
                "event": "drift_protocol_breach",
                "fields": [("state", rv._BREACH_STATE), ("suggestion", rv._BREACH_SUGGESTION),
                           ("retries", retries), ("cycle", cycle)],
                "match": {"cycle": cycle},
            })
        emissions.append({
            "event": "phase_transition", "fields": [("from", "review"), ("to", target)],
            "match": {"from": "review", "to": target},
        })

    elif verb == "spec-approve":
        if decision not in ("approved", "cancelled", "revise"):
            raise _PlanError(f"spec-approve requires a valid --decision, got {decision!r}")
        decision_state = decision
        if decision == "approved":
            emissions = [
                {"event": "spec_approved", "fields": [("decision", "approved")], "match": {}},
            ]
            if emit_transition:
                emissions.append({
                    "event": "phase_transition", "fields": [("from", "specify"), ("to", "plan")],
                    "match": {"from": "specify", "to": "plan"},
                })
            # NOTE: the backend-gated status:refined write-back is Task 14a's
            # monotonic status projection (see _project_status), not the core body.
        elif decision == "cancelled":
            emissions = [{"event": "lifecycle_cancelled", "fields": [], "match": {}}]
        else:  # revise
            emissions = []

    else:  # implement-transition
        resolved_mode = mode or ("batch" if batch is not None else "transition")
        if resolved_mode == "batch":
            if batch is None or tasks is None:
                raise _PlanError("implement-transition batch mode requires --batch and --tasks")
            decision_state = "dispatched"
            emissions = [
                {"event": "batch_dispatch", "fields": [("batch", batch), ("tasks", tasks)],
                 "match": {"batch": batch}},
            ]
        else:  # transition — reuse the B1 §4 routing rule
            route, tier = it._resolve_route(log_path)
            decision_state = route
            emissions = [
                {"event": "phase_transition",
                 "fields": [("from", "implement"), ("to", route), ("tier", tier)],
                 "match": {"from": "implement", "to": route}},
            ]

    # Quoted-utterance payload (Task 14b): land the operator's verbatim consent text
    # field-additively on the consent-bearing legacy rows (plan_approved/spec_approved)
    # ONLY. Additive-only — appended after the arm's own fields, before advance tags
    # the invocation_id at emit time; omitted entirely when no utterance was supplied.
    if consent_utterance is not None:
        for em in emissions:
            if em["event"] in _CONSENT_UTTERANCE_EVENTS:
                em["fields"] = [*em["fields"], (_CONSENT_UTTERANCE_FIELD, consent_utterance)]

    transition = tt.transition_by_arm(owning, decision_state)
    if transition is None:  # pragma: no cover — completeness test pins arm coverage
        raise _PlanError(
            f"no transition-table row for arm ({owning!r}, {decision_state!r})"
        )
    return transition, decision_state, emissions


# ---------------------------------------------------------------------------
# Status projection (Task 14a) — the status lattice, phase→status map, and the
# closed set of demoting events.
# ---------------------------------------------------------------------------

# ADR-0016: status projection is scoped to the cortex-backlog backend ONLY.
_CORTEX_BACKLOG_BACKEND = "cortex-backlog"

# The backlog status advance projects for a transition's DESTINATION lifecycle
# state, keyed by ``Transition.to_state`` (the machine phase advance lands the
# feature in). Values are the canonical backlog vocabulary (the
# ``common.normalize_status`` targets — NOT invented names). A to_state absent
# from this map projects NO status (the projector no-ops): ``research`` /
# ``specify`` are never an advance destination with emissions, and ``escalated``
# carries no unambiguous backlog-status meaning (a human decides), so it is
# deliberately omitted rather than guessed. The ``plan`` → ``refined`` row mirrors
# the standalone-refine write-back precedent (spec_approve._apply_backlog_writeback).
_STATE_TO_STATUS: dict[str, str] = {
    "plan": "refined",
    "implement": "in_progress",
    "implement-rework": "in_progress",
    "review": "in_progress",
    "complete": "complete",
    "cancelled": "abandoned",
}

# The ``lifecycle_phase`` advance projects onto the frontmatter ALONGSIDE status,
# keyed by ``Transition.to_state``. This closes the served-loop half of the #378
# req-5 write-omission: a served-loop completion (``review.approved`` /
# ``implement.complete`` → to_state ``complete``) must advance the item's
# ``lifecycle_phase`` so it tracks status, else the item re-freezes at its prior
# phase (e.g. ``research``). The value is DERIVED from the committed transition's
# to_state, never a blind constant — so a wontfix/cancel transition (to_state
# ``cancelled``, status ``abandoned``) is NOT mislabelled ``complete``. Only the
# terminal ``complete`` is mapped: the non-terminal destinations keep events-first
# phase resolution (their lifecycle dir is live, so ``generate_index`` resolves the
# phase from the log), and ``cancelled`` has no valid ``lifecycle_phase`` value.
_STATE_TO_PHASE: dict[str, str] = {
    "complete": "complete",
}

# The status lattice: a monotonic rank over the canonical backlog vocabulary
# (hazard 4). Projection only ever moves a feature FORWARD — to a rank >= its
# current rank; a move to a strictly LOWER rank is a demotion, refused unless a
# demoting event backs it. The three terminal statuses share the top rank
# (distinct absorbing states — none sits below another). A current status this map
# does not recognise ranks as 0 (the floor), so an unknown/absent status never
# blocks a legitimate forward projection.
_STATUS_RANK: dict[str, int] = {
    "backlog": 0,
    "refined": 1,
    "in_progress": 2,
    "complete": 3,
    "abandoned": 3,
    "superseded": 3,
}

# The closed set of events whose presence in the log AUTHORIZES a status demotion
# (hazard 4). A projection that would lower the lattice rank is refused UNLESS one
# of these backs it: ``lifecycle_cancelled`` / ``feature_wontfix`` genuinely push a
# feature off the forward path (a future reopen event would join this set). Without
# a demoting event, the projector never silently demotes.
_DEMOTING_EVENTS: frozenset[str] = frozenset({"lifecycle_cancelled", "feature_wontfix"})


# ---------------------------------------------------------------------------
# Extension seams (Tasks 14a / 14b) — no-ops in this core body
# ---------------------------------------------------------------------------


def _run_gh(cmd: List[str]) -> Optional[subprocess.CompletedProcess]:
    """The injectable subprocess boundary for the gh cross-check (Task 14b).

    Runs *cmd* and returns the CompletedProcess, or None on any exec failure —
    including ``gh`` not being on PATH (``shutil.which`` probe first, so a machine
    without ``gh`` fails open rather than raising). Tests inject a fake in its place
    (``_consent_cross_check(..., gh_run=fake)`` or ``monkeypatch`` this attribute) so
    the boundary is exercised with NO network. This is the single seam the whole
    cross-check funnels through — the reason the claim/commit split runs side effects
    outside the flock is precisely so this network call never holds the log lock.
    """
    if not cmd or shutil.which(cmd[0]) is None:
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=_GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None


def _gh_pr_state(
    number: int, repo: str, *, run: Optional[Callable[[List[str]], Optional[subprocess.CompletedProcess]]] = None
) -> Optional[str]:
    """Resolve the gh PR ``state`` string (e.g. ``MERGED``/``OPEN``/``CLOSED``) for
    *number*, or None when it cannot be resolved.

    Routes the subprocess through *run* (defaulting to :func:`_run_gh`) so the
    boundary is injectable and CI never touches the network. ``--repo`` pins the
    query to the recorded repo (from the ``pr_opened`` row) even if ``origin`` is
    ambiguous. Any failure — exec error, non-zero exit, unparseable JSON, missing
    ``state`` — collapses to None (the cross-check then fails open; it refuses only on
    a DEFINITE non-merged state, never on an unverifiable one).
    """
    runner = run if run is not None else _run_gh
    cmd = ["gh", "pr", "view", str(number), "--json", "state"]
    if repo:
        cmd += ["--repo", repo]
    proc = runner(cmd)
    if proc is None or proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return None
    state = data.get("state") if isinstance(data, dict) else None
    return state if isinstance(state, str) and state else None


def _pr_ref_from_rows(rows: List[dict]) -> Optional[tuple[int, str]]:
    """Return ``(number, repo)`` for the last ``pr_opened`` row in *rows*, or None
    when no PR is recorded. ``repo`` is ``""`` when the row omits it (the query then
    falls back to the ambient ``origin``). A trunk-mode feature that never opened a PR
    yields None — the merge-consent cross-check then has nothing to verify."""
    number: Optional[int] = None
    repo = ""
    for r in rows:
        if r.get("event") != "pr_opened":
            continue
        n = r.get("number")
        rp = r.get("repo")
        if isinstance(n, int):
            number = n
        if isinstance(rp, str):
            repo = rp
    return (number, repo) if number is not None else None


def _consent_cross_check(
    *, verb: str, transition: tt.Transition, feature: str, log_path: Path, rows: List[dict],
    gh_run: Optional[Callable[[List[str]], Optional[subprocess.CompletedProcess]]] = None,
) -> Optional[dict]:
    """Task 14b: merge-consent gh PR-state cross-check (hazard 5). Runs BETWEEN claim
    and side effects, OUTSIDE the flock (network never under lock — the claim/commit
    split exists for this). Returns a refusal envelope to abort (the claim's
    ``advance_started`` is then a recoverable orphan), else None.

    Fires only for a merge-consent transition (:data:`_MERGE_CONSENT_TRANSITION_IDS`
    — ``review.approved``, review→complete) whose feature carries a recorded PR (a
    ``pr_opened`` row). It cross-checks real gh PR state via the injectable
    :func:`_run_gh` seam (*gh_run* overrides it, so CI mocks the boundary with no
    network) and REFUSES when the PR is in a definite non-merged state — the
    fabricated-attestation defense: a merge that did not actually happen cannot
    advance the feature to complete. Fails OPEN when gh is unresolvable (not on PATH,
    offline, unparseable) or when no PR is recorded (trunk-mode completion): the
    cross-check hardens an EXISTING merge claim, it never invents a PR requirement.
    """
    if transition.id not in _MERGE_CONSENT_TRANSITION_IDS:
        return None
    ref = _pr_ref_from_rows(rows)
    if ref is None:
        return None  # no recorded PR (e.g. trunk-mode completion) — nothing to verify
    number, repo = ref
    state = _gh_pr_state(number, repo, run=gh_run)
    if state is None:
        return None  # gh unverifiable — fail open (best-effort hardening, never network-blocking)
    if state.upper() not in _MERGED_PR_STATES:
        return {
            "reason": (
                f"merge-consent cross-check refused {transition.id} (review→complete): "
                f"recorded PR #{number} is in gh state {state!r}, not merged — a "
                f"fabricated merge attestation cannot advance the feature to complete"
            ),
            "missing_evidence": (
                f"gh PR #{number} in a merged state "
                f"(got {state!r}; expected one of {sorted(_MERGED_PR_STATES)})"
            ),
            "gh_cross_check": {
                "number": number, "repo": repo, "state": state,
                "expected": sorted(_MERGED_PR_STATES),
            },
        }
    return None


def _root_from_log(log_path: Path) -> Optional[Path]:
    """Derive the project root from a standard events.log path
    (``<root>/cortex/lifecycle/<feature>/events.log``).

    Returns the ``<root>`` Path when the log sits under a ``cortex/lifecycle``
    ancestor, else None (a caller-supplied non-standard ``--log-path`` simply
    yields no projection rather than a mis-rooted write).
    """
    parts = Path(log_path).parts
    for i in range(len(parts) - 1):
        if parts[i] == "cortex" and parts[i + 1] == "lifecycle" and i > 0:
            return Path(*parts[:i])
    return None


def _is_archive_shadowed(feature: str, log_path: Path) -> bool:
    """True when an archived duplicate of the feature's lifecycle dir shadows the
    live one (hazard 7).

    The live feature dir is ``log_path.parent``; its lifecycle root is one level
    up. An archived copy at ``<lifecycle_root>/archive/<feature>`` (wontfix_cli's
    archive-move destination) means the feature was archived — the append path
    must refuse and the projector must not write status for it.
    """
    feature_dir = Path(log_path).parent
    lifecycle_root = feature_dir.parent
    return (lifecycle_root / "archive" / feature).exists()


def _has_demoting_event(rows: List[dict]) -> bool:
    """True when *rows* carries an event whose parsed ``event`` field is in
    :data:`_DEMOTING_EVENTS` — the events that authorize a status demotion."""
    return any(r.get("event") in _DEMOTING_EVENTS for r in rows)


def _project_status(
    *, feature: str, transition: tt.Transition, log_path: Path, rows: List[dict],
    project_root: Optional[Path],
) -> Optional[str]:
    """Task 14a: post-commit monotonic status projection (cortex-backlog backend
    only, ADR-0016) with the archive-shadow guard.

    Projects the committed transition onto its cortex-backlog item's frontmatter
    ``status``, but only ever FORWARD on the status lattice (:data:`_STATUS_RANK`):
    a move to a strictly lower rank is a demotion, refused unless a demoting event
    (:data:`_DEMOTING_EVENTS`) backs it (hazard 4). Before any write the append path
    checks for an archive shadow — an archived duplicate of the feature dir under
    ``<lifecycle>/archive/<feature>`` — and refuses (no-op) when the feature is
    shadowed (hazard 7).

    Scoped to the cortex-backlog backend: any other backend is left untouched
    (ADR-0016). Best-effort and never-raising (post-commit side channel — the
    transition already committed, so a projection failure must not crash advance).
    Returns a short outcome tag for observability; the caller ignores it.
    """
    try:
        return _project_status_inner(
            feature=feature, transition=transition, log_path=log_path,
            rows=rows, project_root=project_root,
        )
    except Exception:  # noqa: BLE001 — post-commit projection is strictly best-effort
        return "error"


def _project_status_inner(
    *, feature: str, transition: tt.Transition, log_path: Path, rows: List[dict],
    project_root: Optional[Path],
) -> Optional[str]:
    """The projection body :func:`_project_status` wraps in a never-raise guard."""
    # Only project for a to_state with an unambiguous backlog-status meaning.
    target = _STATE_TO_STATUS.get(transition.to_state)
    if target is None:
        return "skip:no-mapping"

    # Locate the project root: the caller's explicit root wins (test/finalize
    # affordance); else derive it from the standard events.log layout.
    root = Path(project_root) if project_root is not None else _root_from_log(log_path)
    if root is None:
        return "skip:no-root"

    backlog_dir = root / "cortex" / "backlog"
    if not backlog_dir.is_dir():
        return "skip:no-backlog"

    # ADR-0016: status projection is cortex-backlog-only. Any other backend is left
    # untouched — the wheel never writes an external tracker.
    if resolve_backlog_backend(root) != _CORTEX_BACKLOG_BACKEND:
        return "skip:backend"

    # Archive-shadow guard (hazard 7): if an archived copy of the feature dir
    # shadows the live one, the append path refuses and the projector no-ops.
    if _is_archive_shadowed(feature, log_path):
        return "refused:archive-shadow"

    # Resolve the backlog item; an unresolved/ambiguous reference is a silent skip
    # (mirrors spec_approve's no-item semantics) — never a crash. An archived
    # backlog item is not in the active backlog dir, so it resolves to not_found
    # here and is skipped for free.
    result = resolve(feature, backlog_dir)
    if result.status != "ok" or result.item is None:
        return f"skip:{result.status}"
    item = result.item

    # Monotonic-lattice check (hazard 4): read the current status, normalize it onto
    # the canonical vocabulary, and refuse a strictly-demoting move unless a demoting
    # event backs it.
    fm = _parse_frontmatter(item)
    current_raw = fm.get("status")
    current = normalize_status(str(current_raw)) if current_raw else None
    current_rank = _STATUS_RANK.get(current, 0) if current else 0
    target_rank = _STATUS_RANK[target]

    if target_rank < current_rank and not _has_demoting_event(rows):
        return "refused:demotion"

    # Project status and — for the terminal ``complete`` destination — advance
    # lifecycle_phase in the SAME write so a served-loop completion's phase tracks
    # its status (#378 req-5). Derived from the transition, so a cancel/wontfix
    # move (no _STATE_TO_PHASE entry) writes status only, never a stale ``complete``.
    fields: dict[str, str] = {"status": target}
    phase = _STATE_TO_PHASE.get(transition.to_state)
    if phase is not None:
        fields["lifecycle_phase"] = phase
    update_item(item, fields, backlog_dir, session_id=None)
    return f"wrote:{target}"


def _project_spec_areas(
    *, feature: str, backlog_file: Optional[str], spec_path: str,
    areas: Optional[List[str]], clear_areas: bool, log_path: Path,
    project_root: Optional[Path],
) -> Optional[str]:
    """#378 req-7: post-commit projection of the spec-approval write-back's
    ``spec:``/``areas:`` fields — the two fields :func:`_project_status`
    deliberately does NOT touch.

    advance's ``spec-approve`` arm already writes ``status: refined`` for the
    ``to_state == plan`` row via the lattice- and archive-shadow-guarded
    :func:`_project_status` seam (events-first, monotonic). This companion seam
    projects ONLY ``spec`` (the approved spec artifact path) and, preserve-on-omit,
    ``areas`` — so the served verb owns the full write-back the standalone
    ``spec_approve._apply_backlog_writeback`` used to (routing residue from #374)
    WITHOUT re-writing status: re-writing status here would demote an item already
    past ``refined`` on a re-approve/kickback, reintroducing the hazard-4 demotion
    the ``_project_status`` guard prevents.

    Gated through the SAME backend resolution :func:`_project_status` uses —
    self-resolve via ``resolve_backlog_backend(root)`` plus the archive-shadow
    guard, NOT the caller's ``--backend`` flag — so the status write and this
    spec/areas write can never disagree about whether the backend is writable.
    Best-effort and never-raising (post-commit side channel); returns a short
    outcome tag the caller ignores.
    """
    try:
        return _project_spec_areas_inner(
            feature=feature, backlog_file=backlog_file, spec_path=spec_path,
            areas=areas, clear_areas=clear_areas, log_path=log_path,
            project_root=project_root,
        )
    except Exception:  # noqa: BLE001 — post-commit projection is strictly best-effort
        return "error"


def _project_spec_areas_inner(
    *, feature: str, backlog_file: Optional[str], spec_path: str,
    areas: Optional[List[str]], clear_areas: bool, log_path: Path,
    project_root: Optional[Path],
) -> Optional[str]:
    """The body :func:`_project_spec_areas` wraps in a never-raise guard.

    ``areas`` preserve-on-omit: an omitted ``areas`` (``None`` and not
    *clear_areas*) drops the key so ``update_item`` leaves the field untouched;
    ``--clear-areas`` writes ``[]``; a non-empty list writes it — mirroring
    ``spec_approve._apply_backlog_writeback``.
    """
    root = Path(project_root) if project_root is not None else _root_from_log(log_path)
    if root is None:
        return "skip:no-root"

    backlog_dir = root / "cortex" / "backlog"
    if not backlog_dir.is_dir():
        return "skip:no-backlog"

    # Self-resolved backend gate (ADR-0016 / req-7): use the SAME resolution
    # _project_status uses, never the caller's --backend flag — so the status
    # write and this spec/areas write agree on whether the backend is writable.
    if resolve_backlog_backend(root) != _CORTEX_BACKLOG_BACKEND:
        return "skip:backend"

    # Archive-shadow guard (hazard 7): a shadowed feature's item is not written.
    if _is_archive_shadowed(feature, log_path):
        return "refused:archive-shadow"

    # Resolve the item the caller named via --backlog-file (mirroring
    # spec_approve's write shape, which the refine skill passes distinct from
    # --feature); fall back to the feature slug when no basename was supplied. An
    # empty/unresolved/ambiguous reference is a silent skip (post-commit
    # best-effort — never the exit-2 crash the standalone verb raises).
    ref = Path(backlog_file).stem if backlog_file else feature
    if not ref:
        return "skip:no-item"
    result = resolve(ref, backlog_dir)
    if result.status != "ok" or result.item is None:
        return f"skip:{result.status}"

    # Write ONLY spec + (preserve-on-omit) areas — status stays _project_status's.
    fields: dict = {"spec": spec_path}
    if clear_areas:
        fields["areas"] = []
    elif areas:
        fields["areas"] = areas
    update_item(result.item, fields, backlog_dir, session_id=None)
    return "wrote:spec-areas"


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------


def advance(
    *,
    verb: str,
    feature: str,
    from_state: Optional[str] = None,
    log_path: Optional[Path] = None,
    discriminator: str = "",
    decision: Optional[str] = None,
    dispatch_choice: Optional[str] = None,
    verdict: Optional[str] = None,
    cycle: int = 1,
    drift: Optional[str] = None,
    breach: bool = False,
    retries: int = 2,
    emit_transition: bool = False,
    batch: Optional[int] = None,
    tasks: Optional[list] = None,
    mode: Optional[str] = None,
    consent_utterance: Optional[str] = None,
    spec_path: Optional[str] = None,
    backlog_file: Optional[str] = None,
    areas: Optional[List[str]] = None,
    clear_areas: bool = False,
    project_root: Optional[Path] = None,
) -> dict:
    """Execute one composed transition under the claim/commit locking primitive.

    Flow: resolve the arm → derive the deterministic ``invocation_id`` from the
    (feature, from_state, to_state) business tuple → pause-scoping pre-check →
    ``claim_transition`` (gate + ``advance_started``) → consent cross-check seam →
    emit the ordered legacy vocabulary (idempotent, ``invocation_id``-tagged, OUTSIDE
    the flock) → ``commit_transition`` (re-validate + ``advance_committed``) → status
    projection seam. Returns a ``{state, ...}`` envelope; never raises for a handled
    outcome (house style).

    ``from_state`` honours the ``next`` envelope's ``advance_contract.expected_from_state``
    when supplied; omitted, it defaults to the composed arm's table ``from_state``.
    ``log_path`` honours ``advance_contract.log_path``; omitted, it is the pinned
    machine-verb resolver ``resolve_events_log(feature)`` (or, with *project_root*, the
    same-tree log for tests).
    """
    guard = _reject_unsafe_slug(feature)
    if guard is not None:
        return guard

    if verb not in _VERBS:
        return {"state": "error", "message": f"unknown verb {verb!r}, expected {_VERBS}"}

    # Resolve the events.log: the caller's advance_contract path wins; else the
    # pinned machine-verb resolver (worktree-aware, main-root-anchored, R4). A
    # project_root is the test/finalize affordance (log_event uses CWD resolution,
    # so tests hand advance the same-tree path explicitly).
    if log_path is not None:
        resolved_log = Path(log_path)
    elif project_root is not None:
        resolved_log = Path(project_root) / "cortex" / "lifecycle" / feature / "events.log"
    else:
        resolved_log = resolve_events_log(feature)

    try:
        transition, decision_state, emissions = _emission_plan(
            verb=verb, log_path=resolved_log, decision=decision,
            dispatch_choice=dispatch_choice, verdict=verdict, cycle=cycle, drift=drift,
            breach=breach, retries=retries, emit_transition=emit_transition,
            batch=batch, tasks=tasks, mode=mode, consent_utterance=consent_utterance,
        )
    except _PlanError as exc:
        return {"state": "error", "message": exc.message}

    # No-op arms (revise) short-circuit before the primitive — nothing to claim.
    if not emissions:
        return {
            "state": decision_state, "feature": feature, "verb": verb,
            "from_state": transition.from_state, "to_state": transition.to_state,
            "invocation_id": None, "advanced": False, "emitted": [],
        }

    effective_from = from_state if from_state is not None else transition.from_state
    to_state = transition.to_state
    # The business tuple is the STABLE identity (table endpoints), so a crash-recovery
    # retry re-derives the same id and resumes its orphaned claim (never the volatile
    # detected phase, which shifts once the transition lands).
    invocation_id = derive_invocation_id(feature, effective_from, to_state, discriminator)

    rows = _read_rows(resolved_log)

    # Idempotent replay of a COMPLETED advance: if this invocation already committed,
    # short-circuit before claiming. Without this, a re-invocation after the pair
    # resolved would fresh-claim (the primitive treats a committed pair as not open)
    # and append a DUPLICATE advance_started — and, once the phase legitimately moved,
    # would gate-mismatch instead of reporting the benign already-done outcome.
    if _row_present(rows, "advance_committed", {"invocation_id": invocation_id}):
        return {
            "state": decision_state, "feature": feature, "verb": verb,
            "from_state": effective_from, "to_state": to_state,
            "invocation_id": invocation_id, "commit_status": "already-committed",
            "advanced": True, "emitted": [],
        }

    # Pause-scoping pre-check (R12 / hazard 10): refuse to cross an event-backed pause.
    pause = _pause_refusal(rows, invocation_id)
    if pause is not None:
        pause.update({"feature": feature, "verb": verb, "from_state": effective_from,
                      "to_state": to_state, "invocation_id": invocation_id})
        return pause

    # CLAIM — gate the from-state and stake the advance_started row (invocation_id).
    claim = claim_transition(
        feature, effective_from, to_state, invocation_id,
        log_path=resolved_log, extra_fields={"verb": verb},
    )
    if not claim.ok:
        return {
            "state": "refused", "feature": feature, "verb": verb,
            "from_state": effective_from, "to_state": to_state,
            "invocation_id": invocation_id, "claim_status": claim.status,
            "reason": claim.reason,
            "missing_evidence": (
                f"the feature at from_state {effective_from!r} "
                f"(claim {claim.status!r})"
            ),
            "sanctioned_override": _SANCTIONED_OVERRIDE,
            "conflicting_row": claim.conflicting_row,
        }

    # Consent cross-check seam (Task 14b) — OUTSIDE the flock, before side effects.
    objection = _consent_cross_check(
        verb=verb, transition=transition, feature=feature, log_path=resolved_log, rows=rows,
    )
    if objection is not None:
        objection.setdefault("state", "refused")
        objection.setdefault("sanctioned_override", _SANCTIONED_OVERRIDE)
        objection.update({"feature": feature, "verb": verb, "from_state": effective_from,
                          "to_state": to_state, "invocation_id": invocation_id})
        return objection

    # SIDE EFFECTS — emit the ordered legacy vocabulary (dual-emission PRIMARY),
    # each idempotent via a parsed-field existence probe and tagged with the
    # invocation_id so commit's re-reduce recognises them as this claim's own rows.
    emitted: List[str] = []
    for spec in emissions:
        if _row_present(rows, spec["event"], spec["match"]):
            continue
        row_dict: dict = {"event": spec["event"], "feature": feature}
        for key, value in spec["fields"]:
            row_dict[key] = value
        row_dict["invocation_id"] = invocation_id
        log_event_at(resolved_log, row_dict)
        emitted.append(spec["event"])
        rows.append({**row_dict})  # so a later probe in this run sees it

    # COMMIT — re-validate under lock and stake the advance_committed row.
    commit = commit_transition(
        feature, effective_from, to_state, invocation_id,
        log_path=resolved_log, extra_fields={"verb": verb},
    )
    if not commit.ok:
        return {
            "state": "refused", "feature": feature, "verb": verb,
            "from_state": effective_from, "to_state": to_state,
            "invocation_id": invocation_id, "commit_status": commit.status,
            "reason": commit.reason,
            "missing_evidence": (
                "an uninterleaved log since the claim "
                f"(commit {commit.status!r})"
            ),
            "sanctioned_override": _SANCTIONED_OVERRIDE,
            "interleaved_row": commit.interleaved_row,
            "emitted": emitted,
        }

    # Status projection seam (Task 14a) — post-commit, no-op in the core body.
    _project_status(feature=feature, transition=transition, log_path=resolved_log,
                    rows=rows, project_root=project_root)

    # Spec/areas projection seam (#378 req-7) — post-commit, spec-approve/approved
    # ONLY, and only when the caller supplied the write-back (--spec-path). Writes
    # ONLY spec + areas; status stays _project_status-owned (events-first). An
    # emission-only caller that omits --spec-path is unchanged (no projection).
    if verb == "spec-approve" and decision_state == "approved" and spec_path is not None:
        _project_spec_areas(
            feature=feature, backlog_file=backlog_file, spec_path=spec_path,
            areas=areas, clear_areas=clear_areas, log_path=resolved_log,
            project_root=project_root,
        )

    return {
        "state": decision_state, "feature": feature, "verb": verb,
        "from_state": effective_from, "to_state": to_state,
        "invocation_id": invocation_id, "claim_status": claim.status,
        "commit_status": commit.status, "advanced": True, "emitted": emitted,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-advance",
        description=(
            "Execute one composed lifecycle transition (the write side of the served "
            "loop) under the claim/commit locking primitive, dual-emitting the legacy "
            "vocabulary plus the advance_started/advance_committed machine rows. "
            "Always exit 0 with a {state, ...} JSON envelope."
        ),
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
        p.add_argument(
            "--from-state", default=None, metavar="STATE",
            help="Expected from_state (the next envelope's advance_contract.expected_from_state); "
                 "defaults to the arm's table from_state.",
        )
        p.add_argument(
            "--log-path", default=None, metavar="PATH",
            help="Explicit events.log (advance_contract.log_path); defaults to the pinned resolver.",
        )
        p.add_argument(
            "--discriminator", default="", metavar="TOKEN",
            help="Optional per-invocation discriminator for the invocation_id (concurrent "
                 "independent advances of the same edge).",
        )

    def _consent(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--consent-utterance", default=None, metavar="TEXT",
            help="Operator's verbatim consent text (Task 14b, hazard 5); landed "
                 "field-additively on the plan_approved/spec_approved row so a "
                 "fabricated attestation is a specific falsifiable lie.",
        )

    p_plan = sub.add_parser("plan-decision", help="Compose the plan-approval decision.")
    _common(p_plan)
    _consent(p_plan)
    p_plan.add_argument("--decision", required=True,
                        choices=["branch-mode-approved", "wait-approved", "cancelled", "revise"])
    p_plan.add_argument("--dispatch-choice", choices=list(_pd._VALID_MODES), default=None)

    p_review = sub.add_parser("review-verdict", help="Compose the review-verdict tail.")
    _common(p_review)
    p_review.add_argument("--verdict", required=True, choices=list(rv._VERDICTS))
    p_review.add_argument("--cycle", required=True, type=int, metavar="N")
    p_review.add_argument("--drift", required=True, choices=list(rv._DRIFT_VALUES))
    p_review.add_argument("--breach", action="store_true")
    p_review.add_argument("--retries", type=int, default=2, metavar="N")

    p_spec = sub.add_parser("spec-approve", help="Compose the spec-approval decision.")
    _common(p_spec)
    _consent(p_spec)
    p_spec.add_argument("--decision", required=True, choices=["approved", "cancelled", "revise"])
    grp = p_spec.add_mutually_exclusive_group()
    grp.add_argument("--emit-transition", dest="emit_transition", action="store_true")
    grp.add_argument("--no-emit-transition", dest="emit_transition", action="store_false")
    p_spec.set_defaults(emit_transition=False)
    # #378 req-7: spec/areas write-back projection args (status stays
    # _project_status-owned). --spec-path is the write-back trigger; an
    # emission-only caller that omits it keeps the pre-req-7 behavior. --backend
    # is accepted for interface parity with the refine caller but does NOT gate
    # the write — the projection self-resolves the backend (resolve_backlog_backend)
    # so it can never disagree with _project_status's status write.
    p_spec.add_argument(
        "--spec-path", default=None, metavar="PATH",
        help="Spec artifact path projected onto the item's spec frontmatter field "
             "(triggers the spec/areas write-back; omit for emission-only).",
    )
    p_spec.add_argument(
        "--backend", default=None, metavar="BACKEND",
        help="Accepted for interface parity with the refine caller; the write-back "
             "self-resolves the backend (resolve_backlog_backend), so this value "
             "does NOT gate the projection.",
    )
    p_spec.add_argument(
        "--backlog-file", default=None, metavar="BASENAME",
        help="Resolver basename of the backlog item to project spec/areas onto "
             "(e.g. 326-foo.md); defaults to the feature slug when omitted.",
    )
    p_spec.add_argument(
        "--areas", nargs="*", default=None, metavar="AREA",
        help="Areas to set (preserve-on-omit; omission leaves areas untouched).",
    )
    p_spec.add_argument(
        "--clear-areas", action="store_true",
        help="Explicit sentinel to clear the areas field (omission never clears).",
    )

    p_impl = sub.add_parser("implement-transition", help="Compose an implement-cluster emission.")
    _common(p_impl)
    p_impl.add_argument("--mode", choices=list(it._MODES), default=None)
    p_impl.add_argument("--batch", type=int, default=None, metavar="N")
    p_impl.add_argument("--tasks", type=_json_arg, default=None, metavar="JSON")

    return parser


def _json_arg(value: str) -> object:
    """argparse ``type=`` for the JSON-typed ``--tasks`` field."""
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON value {value!r}: {exc}")


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-advance")
    args = _build_parser().parse_args(argv)
    kwargs: dict = {
        "verb": args.verb,
        "feature": args.feature,
        "from_state": args.from_state,
        "log_path": Path(args.log_path) if args.log_path else None,
        "discriminator": args.discriminator,
    }
    if args.verb == "plan-decision":
        kwargs.update(decision=args.decision, dispatch_choice=args.dispatch_choice,
                      consent_utterance=args.consent_utterance)
    elif args.verb == "review-verdict":
        kwargs.update(verdict=args.verdict, cycle=args.cycle, drift=args.drift,
                      breach=args.breach, retries=args.retries)
    elif args.verb == "spec-approve":
        # --backend is parsed for interface parity but intentionally NOT forwarded:
        # the spec/areas projection self-resolves the backend (req-7).
        kwargs.update(decision=args.decision, emit_transition=args.emit_transition,
                      consent_utterance=args.consent_utterance,
                      spec_path=args.spec_path, backlog_file=args.backlog_file,
                      areas=args.areas, clear_areas=args.clear_areas)
    elif args.verb == "implement-transition":
        kwargs.update(mode=args.mode, batch=args.batch, tasks=args.tasks)

    try:
        result = advance(**kwargs)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    result["protocol"] = PROTOCOL_VERSION
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
