"""CLI helper for appending events to a feature's events.log.

Exposes a generic ``log`` subcommand plus one high-level subcommand per
non-exempt lifecycle event (``phase-transition``, ``review-verdict``, …). The
high-level subcommands own their event's field contract (names, order, type,
enum) so callers emit without restating the raw scaffold; each funnels into the
same ``log_event`` writer, so the row is identical to the equivalent ``log``
form. See ``_EVENT_SUBCOMMANDS`` for the table and the ADR-0020 exempt-event
carve-out. The generic form:

    cortex-lifecycle-event log --event <name> --feature <slug> \
        [--set k=v ...] [--set-json k=v ...]

Path resolution uses ``_resolve_user_project_root_from_cwd()`` (ignores
``CORTEX_REPO_ROOT``), so the log target follows the physical CWD — the
intended behaviour when the orchestrator session has cd'd into a worktree.

Write discipline: append-only under an exclusive sibling-lockfile
``fcntl.flock`` with ``O_APPEND`` — the events.log is append-only JSONL and
each call writes exactly one row, so no read-modify-write is performed (see
``cortex/requirements/pipeline.md`` L143/146/151 for the atomicity,
audit-trail, and locking constraints this satisfies).

JSONL row schema::

    {
        "ts": "<ISO 8601 UTC, second-precision Z>",
        "event": "<event-name>",
        "feature": "<feature-slug>",
        <ordered extra fields from --set / --set-json>
    }

The three base keys are emitted first, then any extra fields in argv order.
``--set k=v`` records the literal string ``v``; ``--set-json k=v`` parses ``v``
with ``json.loads`` (int/bool/null/array/object). Duplicate keys are
last-wins. Serialization uses ``json.dumps`` spaced defaults.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, NamedTuple, Optional

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
    resolve_lifecycle_phase,
)
from cortex_command.lifecycle.log_resolver import resolve_events_log


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as ``%Y-%m-%dT%H:%M:%SZ``."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events_log_path(feature_slug: str) -> Path:
    """Resolve the events.log path using the CWD-based root resolver.

    Raises ``CortexProjectRootError`` when the root cannot be resolved.
    """
    root = _resolve_user_project_root_from_cwd()
    return root / "cortex" / "lifecycle" / feature_slug / "events.log"


def _append_event_atomic(log_path: Path, row: str) -> None:
    """Append *row* to *log_path* under an exclusive sibling-lockfile flock.

    Protocol:
        1. Create the parent directory if absent.
        2. Open (or create) a sibling lock file ``{log_path}.lock`` and
           acquire an exclusive advisory ``fcntl.flock`` on it.
        3. Open *log_path* with ``O_WRONLY | O_CREAT | O_APPEND`` and write the
           single *row*; ``O_APPEND`` positions every write at end-of-file.
        4. Release the flock (close the lock fd).

    The events.log is append-only, so there is no read-modify-write step. The
    flock serialises this verb's own concurrent invocations; ``O_APPEND`` keeps
    a write atomic against an unlocked bare appender for the common bounded row.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = log_path.parent / f"{log_path.name}.lock"

    lock_fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC,
        0o600,
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            target_fd = os.open(
                log_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC,
                0o644,
            )
            try:
                os.write(target_fd, row.encode("utf-8"))
            finally:
                os.close(target_fd)
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_event_at(log_path: Path, event_dict: dict) -> None:
    """Append one event row to an *explicit* events.log path under the shared
    sibling-lockfile flock discipline.

    For writers that resolve the feature log themselves (e.g. the pipeline
    review dispatch with a config-supplied lifecycle base, or the interactive
    lock's main-root-anchored telemetry) and therefore cannot use
    ``log_event``'s CWD resolution. A ``ts`` field is prepended when absent;
    the caller supplies ``event``/``feature`` keys and any ordered fields.
    """
    row_dict = {"ts": _now_iso()}
    row_dict.update(event_dict)
    _append_event_atomic(log_path, json.dumps(row_dict) + "\n")


def log_event(
    event: str,
    feature: str,
    fields: Optional[list[tuple[str, str, object]]] = None,
) -> None:
    """Append one event row to ``cortex/lifecycle/{feature}/events.log``.

    Path is resolved from the physical CWD (ignores ``CORTEX_REPO_ROOT``).

    Args:
        event: Event name string (e.g. ``"interactive_worktree_entered"``).
        feature: Feature slug (e.g. ``"my-feature"``).
        fields: Optional ordered ``(kind, key, value)`` triples appended after
            the ``ts``/``event``/``feature`` base keys. ``value`` is already
            typed by the caller; ``kind`` is retained only for symmetry with
            the flag surface. Keys are emitted in order; duplicate keys are
            last-wins.

    Raises:
        CortexProjectRootError: When the project root cannot be resolved
            from the current working directory.
    """
    log_path = _events_log_path(feature)
    row_dict: dict = {
        "ts": _now_iso(),
        "event": event,
        "feature": feature,
    }
    for _kind, key, value in fields or []:
        row_dict[key] = value
    row = json.dumps(row_dict) + "\n"
    _append_event_atomic(log_path, row)


# ---------------------------------------------------------------------------
# Claim/commit transition primitive (374 R3 — hold-lock read-validate-append)
# ---------------------------------------------------------------------------
#
# ``_append_event_atomic`` above is append-ONLY: it flocks the sibling lockfile,
# does one O_APPEND write, unlocks — it never reads under the lock. That is
# unsafe for a transition *decision*, because two deciders can each read the
# same pre-state and each append a conflicting transition (adversarial
# finding 1). The claim/commit primitive below closes that hole: it holds the
# SAME sibling-lock (``{events_log}.lock``, resolved via Task 5's
# ``resolve_events_log`` so every machine verb shares one flock domain) across
# read + validate + append.
#
# Two-phase protocol (the split into two lock acquisitions exists precisely so
# network/subprocess side effects — e.g. a ``gh`` call — NEVER run under flock):
#
#   1. CLAIM   — one critical section: reduce -> from_state gate-check ->
#                append ``advance_started``. A second claimant that sees an
#                unresolved ``advance_started`` (started, not yet committed) for
#                the same ``(feature, from_state)`` under a DIFFERENT
#                ``invocation_id`` is refused with "in-flight transition". The
#                same ``invocation_id`` is the caller's own prior claim (a
#                crash-recovery retry) and resumes idempotently.
#   2. (caller runs side effects OUTSIDE the lock, made idempotent via
#      existence probes — this primitive owns only the two lock phases.)
#   3. COMMIT  — re-acquire the lock, re-read, assert no state-moving row landed
#                after this claim's ``advance_started`` (naming the interleaved
#                row if one did — "state moved since claim"), then append
#                ``advance_committed``. An ``advance_committed`` already present
#                for this ``invocation_id`` resumes idempotently.
#
# Both rows carry the deterministic ``invocation_id`` (business-derived,
# generated once, reused across retries) and so link the pair. Row
# serialization is canonical (``json.dumps(row) + "\n"``, default spacing) so
# the rows parse identically to the typed subcommand rows.

# Events that move the reduced lifecycle state OR the detected phase. A row of
# one of these kinds landing after a claim's ``advance_started`` means the
# ground the claim gated on has shifted — commit must refuse and name it.
# ``advance_started`` is deliberately absent: a bare claim is in-flight, not a
# state move (and the flock refuses a competing claim before it can land here).
_STATE_MOVING_EVENTS: frozenset[str] = frozenset(
    {
        "phase_transition",
        "review_verdict",
        "spec_approved",
        "plan_approved",
        "feature_complete",
        "feature_wontfix",
        "feature_paused",
        "lifecycle_start",
        "criticality_override",
        "complexity_override",
        "advance_committed",
    }
)


class ClaimResult(NamedTuple):
    """Outcome of :func:`claim_transition`.

    Attributes:
        ok: True iff the transition is claimed and the caller may run side
            effects and then :func:`commit_transition`.
        status: ``"claimed"`` (fresh ``advance_started`` appended),
            ``"resumed"`` (this ``invocation_id`` already had an unresolved
            claim — idempotent retry, no duplicate row written),
            ``"in-flight"`` (a different claimant holds an unresolved claim for
            the same ``(feature, from_state)`` — refused), or
            ``"gate-mismatch"`` (the detected phase is not *from_state* —
            refused).
        invocation_id: The deterministic id echoed back, persisted in both rows.
        from_state: The gated from-state.
        log_path: The resolved events.log this claim was written against.
        reason: Human-readable message; ``None`` on success.
        conflicting_row: On ``"in-flight"``, the unresolved ``advance_started``
            row (parsed dict) held by the other claimant; else ``None``.
    """

    ok: bool
    status: str
    invocation_id: str
    from_state: str
    log_path: Path
    reason: Optional[str]
    conflicting_row: Optional[dict]


class CommitResult(NamedTuple):
    """Outcome of :func:`commit_transition`.

    Attributes:
        ok: True iff ``advance_committed`` is now durably in the log for this
            ``invocation_id`` (freshly appended, or already present).
        status: ``"committed"`` (row appended), ``"already-committed"``
            (idempotent — a matching ``advance_committed`` was already present),
            ``"state-moved"`` (a state-moving row interleaved since the claim —
            refused), or ``"no-claim"`` (no matching ``advance_started`` for
            this ``invocation_id`` — refused).
        invocation_id: The deterministic id echoed back.
        log_path: The resolved events.log this commit was validated against.
        reason: Human-readable message; ``None`` on success.
        interleaved_row: On ``"state-moved"``, the offending state-moving row
            (parsed dict) that landed after the claim, when one is nameable;
            else ``None``.
    """

    ok: bool
    status: str
    invocation_id: str
    log_path: Path
    reason: Optional[str]
    interleaved_row: Optional[dict]


def derive_invocation_id(
    feature: str,
    from_state: str,
    to_state: str,
    discriminator: str = "",
) -> str:
    """Derive a deterministic ``invocation_id`` for a transition.

    Same inputs -> same id, so a crash-recovery retry of the *same* logical
    advance re-derives its own id and resumes its orphaned claim. Two
    genuinely-independent concurrent advances of the same edge must differ, so
    a caller that needs them distinguished passes a per-invocation
    *discriminator* (e.g. a session nonce); with an empty discriminator the id
    is the pure business tuple.

    Returns a short hex digest (business-derived, opaque to the reducer).
    """
    payload = "\x1f".join((feature, from_state, to_state, discriminator))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@contextmanager
def _hold_events_lock(log_path: Path) -> Iterator[None]:
    """Hold an exclusive ``fcntl.flock`` on ``{log_path}.lock`` for the block.

    The SAME sibling-lockfile discipline as :func:`_append_event_atomic`, but
    held across an arbitrary read+validate+append body rather than a single
    write — this is what lets the claim/commit primitive read under the lock.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = log_path.parent / f"{log_path.name}.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass


def _append_row_locked(log_path: Path, row_dict: dict) -> None:
    """Append one canonical JSONL row to *log_path* WITHOUT taking the lock.

    Must be called only while :func:`_hold_events_lock` is held. ``O_APPEND``
    keeps the single write at end-of-file; serialization is canonical
    (``json.dumps(row) + "\\n"``, default spacing) so the row parses identically
    to a typed-subcommand row.
    """
    target_fd = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC,
        0o644,
    )
    try:
        os.write(target_fd, (json.dumps(row_dict) + "\n").encode("utf-8"))
    finally:
        os.close(target_fd)


def _read_event_rows(log_path: Path) -> list[dict]:
    """Read *log_path* into an ordered list of parsed dict rows.

    Tolerant like ``common.reduce_lifecycle_state``: a missing file yields an
    empty list; a torn line or a non-dict JSON value is skipped, never raised.
    Intended to be called under :func:`_hold_events_lock`.
    """
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, OSError):
        return []
    rows: list[dict] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _row_summary(row: dict) -> str:
    """Compact, deterministic one-line rendering of a row for refusal messages."""
    return json.dumps(row, sort_keys=True)


def claim_transition(
    feature: str,
    from_state: str,
    to_state: str,
    invocation_id: str,
    *,
    log_path: Optional[Path] = None,
    extra_fields: Optional[dict] = None,
) -> ClaimResult:
    """Phase 1 of the two-phase transition: gate the from-state and stake a claim.

    Holds the events.log flock across reduce -> from_state gate-check -> append
    of a single ``advance_started`` row. Refuses a second claimant that sees an
    unresolved ``advance_started`` for the same ``(feature, from_state)`` under a
    different ``invocation_id`` ("in-flight transition"); the same
    ``invocation_id`` resumes an orphaned claim idempotently (crash recovery).

    Args:
        feature: Feature slug.
        from_state: The lifecycle phase the caller expects to transition FROM;
            gated against ``resolve_lifecycle_phase(...)["phase"]`` (events-first,
            ADR-0025 — never the legacy artifact detector; see the gate comment).
        to_state: The target phase (recorded in both rows for the audit pair).
        invocation_id: Deterministic id (see :func:`derive_invocation_id`),
            persisted in both the ``advance_started`` and ``advance_committed``
            rows to link them.
        log_path: Optional explicit events.log; defaults to the machine-verb
            resolver ``resolve_events_log(feature)`` (Task 5) so claim, commit,
            and the verbs share one flock domain.
        extra_fields: Optional additive fields merged into the ``advance_started``
            row after the base keys (e.g. an audit note). Never overrides a base
            key.

    Returns:
        A :class:`ClaimResult`. ``ok`` is True for ``"claimed"``/``"resumed"``.
    """
    resolved = log_path if log_path is not None else resolve_events_log(feature)
    feature_dir = resolved.parent

    with _hold_events_lock(resolved):
        rows = _read_event_rows(resolved)
        committed_ids = {
            r.get("invocation_id")
            for r in rows
            if r.get("event") == "advance_committed"
        }

        own_open_claim = False
        for r in rows:
            if r.get("event") != "advance_started":
                continue
            if r.get("feature") != feature or r.get("from_state") != from_state:
                continue
            rid = r.get("invocation_id")
            if rid in committed_ids:
                continue  # resolved pair — not in-flight
            if rid == invocation_id:
                own_open_claim = True
                continue
            # A different claimant holds an unresolved claim on this edge.
            return ClaimResult(
                ok=False,
                status="in-flight",
                invocation_id=invocation_id,
                from_state=from_state,
                log_path=resolved,
                reason=(
                    "in-flight transition: an unresolved advance_started for "
                    f"({feature!r}, from_state={from_state!r}) is held by "
                    f"invocation_id={rid!r}: {_row_summary(r)}"
                ),
                conflicting_row=r,
            )

        if own_open_claim:
            # Idempotent resume of this invocation's own orphaned claim — the
            # from_state gate already passed when the claim was first staked.
            return ClaimResult(
                ok=True,
                status="resumed",
                invocation_id=invocation_id,
                from_state=from_state,
                log_path=resolved,
                reason=None,
                conflicting_row=None,
            )

        # Fresh claim: gate the from_state against the events-first resolved
        # phase (ADR-0025). This MUST NOT use detect_lifecycle_phase: that
        # artifact-presence derivation is the LEGACY FALLBACK, and it reports
        # `review` the moment plan.md's tasks are all `[x]`. Since implement.md
        # §2d flips those checkboxes *before* §4 calls the implement-transition
        # verb, gating on it made the implement->review claim unfireable by
        # construction — its precondition was its own refusal condition.
        # Event-driven transitions were unaffected (each verb stakes its claim
        # before emitting the event that moves the detector), which is why this
        # surfaced only on the one artifact-driven boundary.
        phase = resolve_lifecycle_phase(feature_dir).get("phase")
        if phase != from_state:
            return ClaimResult(
                ok=False,
                status="gate-mismatch",
                invocation_id=invocation_id,
                from_state=from_state,
                log_path=resolved,
                reason=(
                    f"from_state gate: detected phase {phase!r} does not match "
                    f"expected from_state {from_state!r}"
                ),
                conflicting_row=None,
            )

        row: dict = {
            "ts": _now_iso(),
            "event": "advance_started",
            "feature": feature,
            "from_state": from_state,
            "to_state": to_state,
            "invocation_id": invocation_id,
        }
        for key, value in (extra_fields or {}).items():
            if key not in row:
                row[key] = value
        _append_row_locked(resolved, row)

        return ClaimResult(
            ok=True,
            status="claimed",
            invocation_id=invocation_id,
            from_state=from_state,
            log_path=resolved,
            reason=None,
            conflicting_row=None,
        )


def commit_transition(
    feature: str,
    from_state: str,
    to_state: str,
    invocation_id: str,
    *,
    log_path: Optional[Path] = None,
    extra_fields: Optional[dict] = None,
) -> CommitResult:
    """Phase 3 of the two-phase transition: re-validate under lock and commit.

    Re-acquires the events.log flock, re-reads, and asserts that no state-moving
    row landed after this invocation's ``advance_started``. If one did, refuses
    with "state moved since claim" and names the interleaved row. Otherwise
    appends the ``advance_committed`` row that closes the pair. Idempotent: a
    matching ``advance_committed`` already present returns success without a
    duplicate write.

    Args:
        feature: Feature slug.
        from_state / to_state: Echoed into the ``advance_committed`` row.
        invocation_id: The same deterministic id used at claim time.
        log_path: Optional explicit events.log; defaults to
            ``resolve_events_log(feature)``.
        extra_fields: Optional additive fields merged after the base keys.

    Returns:
        A :class:`CommitResult`. ``ok`` is True for
        ``"committed"``/``"already-committed"``.
    """
    resolved = log_path if log_path is not None else resolve_events_log(feature)

    with _hold_events_lock(resolved):
        rows = _read_event_rows(resolved)

        # Idempotent: already committed for this invocation?
        for r in rows:
            if (
                r.get("event") == "advance_committed"
                and r.get("invocation_id") == invocation_id
            ):
                return CommitResult(
                    ok=True,
                    status="already-committed",
                    invocation_id=invocation_id,
                    log_path=resolved,
                    reason=None,
                    interleaved_row=None,
                )

        # Locate this invocation's claim (position anchors "since the claim").
        claim_index: Optional[int] = None
        for index, r in enumerate(rows):
            if (
                r.get("event") == "advance_started"
                and r.get("invocation_id") == invocation_id
            ):
                claim_index = index
        if claim_index is None:
            return CommitResult(
                ok=False,
                status="no-claim",
                invocation_id=invocation_id,
                log_path=resolved,
                reason=(
                    "commit refused: no advance_started claim found for "
                    f"invocation_id={invocation_id!r} — claim first"
                ),
                interleaved_row=None,
            )

        # Any state-moving row after the claim means the ground shifted.
        for r in rows[claim_index + 1:]:
            if r.get("invocation_id") == invocation_id:
                continue  # this invocation's own rows are not interleavers
            if r.get("event") in _STATE_MOVING_EVENTS:
                return CommitResult(
                    ok=False,
                    status="state-moved",
                    invocation_id=invocation_id,
                    log_path=resolved,
                    reason=(
                        "state moved since claim: interleaved "
                        f"{r.get('event')!r} row landed after advance_started: "
                        f"{_row_summary(r)}"
                    ),
                    interleaved_row=r,
                )

        row: dict = {
            "ts": _now_iso(),
            "event": "advance_committed",
            "feature": feature,
            "from_state": from_state,
            "to_state": to_state,
            "invocation_id": invocation_id,
        }
        for key, value in (extra_fields or {}).items():
            if key not in row:
                row[key] = value
        _append_row_locked(resolved, row)

        return CommitResult(
            ok=True,
            status="committed",
            invocation_id=invocation_id,
            log_path=resolved,
            reason=None,
            interleaved_row=None,
        )


# ---------------------------------------------------------------------------
# Console-script entry point
# ---------------------------------------------------------------------------


class _SetFieldAction(argparse.Action):
    """Collect repeated ``--set`` / ``--set-json`` tokens into one ordered list.

    Both flags write ``(kind, key, value)`` triples to a single shared ``dest``
    so interleaved argv order is preserved. ``kind`` is ``"str"`` for ``--set``
    (literal string value) or ``"json"`` for ``--set-json`` (``json.loads``-
    parsed). Each token splits on the **first** ``=`` only; a ``=``-less token
    or a malformed ``--set-json`` value is an argparse usage error (exit != 0),
    raised at parse time before any row is written.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        kind = "json" if option_string == "--set-json" else "str"
        if "=" not in values:
            parser.error(
                f"argument {option_string}: expected KEY=VALUE, got {values!r}"
            )
        key, value_str = values.split("=", 1)
        if not key:
            parser.error(
                f"argument {option_string}: empty key in {values!r}"
            )
        if kind == "json":
            try:
                value: object = json.loads(value_str)
            except json.JSONDecodeError as exc:
                parser.error(
                    f"argument {option_string}: invalid JSON value for "
                    f"key {key!r}: {exc}"
                )
        else:
            value = value_str
        items = getattr(namespace, self.dest, None)
        if items is None:
            items = []
            setattr(namespace, self.dest, items)
        items.append((kind, key, value))


# ---------------------------------------------------------------------------
# High-level event subcommands (ADR-0020 field-set ownership)
# ---------------------------------------------------------------------------
# Each subcommand owns one event's field contract — the field names, their
# order, type, and enum — so a caller emits it without restating the raw
# ``--event <name> --set k=v`` scaffold. Every subcommand funnels into
# ``log_event`` so the emitted row is key/value/type-identical to the
# equivalent ``log`` form (extra-field serialization order is normalized per
# subcommand; consumers key by name, and ADR-0020 fixes only the ts/event/
# feature base-key prefix). The generic ``log`` subcommand is retained as the
# escape hatch and the ONLY path for the ADR-0020 hand-written exempt events
# (``plan_comparison``, ``clarify_critic``, ``pr_opened``) whose canonical
# shape places ``schema_version`` before ``feature``.
#
# The subcommand name is the event name with ``_`` rendered as ``-``. Each
# FieldSpec is ``(flag, emit_key, kind, required, choices)``: ``flag`` is the
# argparse option, ``emit_key`` the row key it writes (they differ only where
# the flag is an ergonomic alias — e.g. ``--drift`` → ``requirements_drift``),
# ``kind`` is ``"str"`` (literal) or ``"json"`` (``json.loads``-parsed, the old
# ``--set-json``), ``choices`` validates the enum or is ``None``.

_STR = "str"
_JSON = "json"

_CRITICALITY = ("low", "medium", "high", "critical")

_EVENT_SUBCOMMANDS: dict[str, tuple[str, list]] = {
    "phase-transition": ("phase_transition", [
        ("--from", "from", _STR, True, None),
        ("--to", "to", _STR, True, None),
        ("--tier", "tier", _STR, False, ("simple", "complex")),
    ]),
    "plan-approved": ("plan_approved", [
        ("--dispatch-choice", "dispatch_choice", _STR, True,
         ("trunk", "worktree-interactive", "feature-branch", "wait")),
    ]),
    "feature-complete": ("feature_complete", [
        ("--tasks-total", "tasks_total", _JSON, False, None),
        ("--rework-cycles", "rework_cycles", _JSON, False, None),
        ("--merge-anchor", "merge_anchor", _STR, False, ("merge", "review")),
    ]),
    "spec-approved": ("spec_approved", [
        ("--decision", "decision", _STR, False, ("approved",)),
    ]),
    "review-verdict": ("review_verdict", [
        ("--verdict", "verdict", _STR, True,
         ("APPROVED", "CHANGES_REQUESTED", "REJECTED")),
        ("--cycle", "cycle", _JSON, True, None),
        ("--drift", "requirements_drift", _STR, True, ("none", "detected")),
    ]),
    "lifecycle-start": ("lifecycle_start", [
        ("--tier", "tier", _STR, True, ("simple", "complex")),
        ("--criticality", "criticality", _STR, True, _CRITICALITY),
    ]),
    "critical-review-skipped": ("lifecycle_critical_review_skipped", [
        ("--phase", "phase", _STR, True, None),
        ("--tier", "tier", _STR, True, ("simple", "complex")),
        ("--criticality", "criticality", _STR, True, _CRITICALITY),
    ]),
    "interactive-worktree-entered": ("interactive_worktree_entered", [
        ("--worktree-path", "worktree_path", _STR, True, None),
    ]),
    "feature-paused": ("feature_paused", [
        # 374 R5: field-additive per-pause accountability. Both optional so
        # legacy kind-absent/slug-less rows still parse; a kind-absent row
        # reduces to the most-restrictive kind (relayed-consent) — hazard 3.
        ("--slug", "slug", _STR, False, None),
        ("--kind", "kind", _STR, False,
         ("question", "phase-exit-wait", "config-conditional", "relayed-consent")),
    ]),
    "lifecycle-cancelled": ("lifecycle_cancelled", []),
    "drift-protocol-breach": ("drift_protocol_breach", [
        ("--state", "state", _STR, True, None),
        ("--suggestion", "suggestion", _STR, True, None),
        ("--retries", "retries", _JSON, True, None),
        # Optional cycle qualifier (additive, epic 371 Phase B follow-up): lets a
        # per-cycle presence check distinguish a genuine second-cycle breach from
        # the first — a review can breach at cycle 1 AND a later cycle.
        ("--cycle", "cycle", _JSON, False, None),
    ]),
    "criticality-override": ("criticality_override", [
        ("--from", "from", _STR, True, None),
        ("--to", "to", _STR, True, None),
    ]),
    "batch-dispatch": ("batch_dispatch", [
        ("--batch", "batch", _JSON, True, None),
        ("--tasks", "tasks", _JSON, True, None),
    ]),
}


def _json_arg(value: str) -> object:
    """argparse ``type=`` for JSON-typed fields (old ``--set-json`` semantics)."""
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid JSON value {value!r}: {exc}"
        )


def _flag_dest(flag: str) -> str:
    """Derive argparse's dest from an option flag (``--tasks-total`` → ``tasks_total``)."""
    return flag[2:].replace("-", "_")


def _emit_subcommand(command: str, args: argparse.Namespace) -> int:
    """Map a high-level event subcommand's parsed args to a ``log_event`` call."""
    event_name, specs = _EVENT_SUBCOMMANDS[command]
    fields: list[tuple[str, str, object]] = []
    for flag, emit_key, kind, required, _choices in specs:
        value = getattr(args, _flag_dest(flag))
        if value is None and not required:
            continue  # optional flag omitted — drop the field entirely
        fields.append((kind, emit_key, value))
    try:
        log_event(event=event_name, feature=args.feature, fields=fields)
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-event: {exc}\n")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-event",
        description="Append events to a feature's events.log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for command, (event_name, specs) in _EVENT_SUBCOMMANDS.items():
        event_p = sub.add_parser(
            command, help=f"Emit a {event_name} event"
        )
        event_p.add_argument(
            "--feature", required=True, metavar="SLUG",
            help="Feature slug (e.g. my-feature)",
        )
        for flag, emit_key, kind, required, choices in specs:
            kwargs: dict = {"required": required}
            if choices is not None:
                kwargs["choices"] = list(choices)
            else:
                kwargs["metavar"] = emit_key.upper()
            if kind == _JSON:
                kwargs["type"] = _json_arg
            event_p.add_argument(flag, **kwargs)

    log_p = sub.add_parser("log", help="Append one event row to events.log")
    log_p.add_argument(
        "--event",
        required=True,
        metavar="NAME",
        help="Event name (e.g. interactive_worktree_entered)",
    )
    log_p.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug (e.g. my-feature)",
    )
    log_p.add_argument(
        "--set",
        dest="set_fields",
        action=_SetFieldAction,
        default=None,
        metavar="KEY=VALUE",
        help="Add a literal string field (repeatable; argv order preserved)",
    )
    log_p.add_argument(
        "--set-json",
        dest="set_fields",
        action=_SetFieldAction,
        default=None,
        metavar="KEY=VALUE",
        help="Add a JSON-typed field parsed via json.loads (repeatable)",
    )
    return parser


def _run(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in _EVENT_SUBCOMMANDS:
        return _emit_subcommand(args.command, args)

    if args.command == "log":
        try:
            log_event(
                event=args.event,
                feature=args.feature,
                fields=args.set_fields,
            )
        except CortexProjectRootError as exc:
            sys.stderr.write(f"cortex-lifecycle-event: {exc}\n")
            return 1
        return 0

    # Unreachable (argparse requires subcommand), but satisfies type checker.
    return 1


def main(argv: Optional[list[str]] = None) -> None:
    sys.exit(_run(argv))


if __name__ == "__main__":
    main()
