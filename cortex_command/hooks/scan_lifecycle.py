"""SessionStart lifecycle scanner.

Implements the ``cortex hooks scan-lifecycle`` subcommand. Reads a Claude
Code SessionStart hook JSON payload on stdin (containing ``session_id``
and ``cwd``), then performs lifecycle-state detection, session-state
mutation, phase encoding, and ``hookSpecificOutput`` emission to inject
lifecycle context into the session.

This module is the Python port of ``hooks/cortex-scan-lifecycle.sh`` per
the resolve-cortex-interpreter-via-cli feature. The skeleton currently
parses input and exits 0 with no output; subsequent tasks fill in the
behavior progressively.

Imports of ``cortex_command.common`` and other intra-package modules are
kept inside the functions that need them (lazy-load discipline per the
overnight precedent at ``cortex_command/cli.py:48-66``), so ``--help``
and trivial dispatch paths do not pay the cost of the full package graph.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cortex_command.hooks._pipeline_state import PipelineState


def _encode_phase(phase: str, checked: int, total: int, cycle: int) -> str:
    """Encode (phase, checked, total, cycle) into the wire-format string.

    Mirrors the bash ``encode_phase`` helper at
    ``hooks/cortex-scan-lifecycle.sh`` lines 184-200. Pure function: no
    I/O, no side effects. Downstream code consumes the encoded string to
    produce phase labels like ``"Phase: Implement (3/5 tasks done)"``.

    Encoding rules per R3:

    * ``phase == "implement"`` and ``total > 0``  -> ``"implement:<checked>/<total>"``
    * ``phase == "implement"`` and ``total == 0`` -> ``"implement:0/0"``
    * ``phase == "implement-rework"``             -> ``"implement-rework:<cycle>"``
    * any other phase                             -> bare ``phase`` string

    Parameters
    ----------
    phase:
        Lifecycle phase identifier (e.g. ``"research"``, ``"implement"``,
        ``"implement-rework"``).
    checked:
        Number of completed implementation tasks.
    total:
        Total implementation tasks.
    cycle:
        Implement-rework cycle index.

    Returns
    -------
    str
        The wire-format encoded phase string.
    """

    if phase == "implement":
        if total > 0:
            return f"implement:{checked}/{total}"
        return "implement:0/0"
    if phase == "implement-rework":
        return f"implement-rework:{cycle}"
    return phase


def _phase_label(encoded_phase: str) -> str:
    """Translate an encoded phase string into a human-readable label.

    Mirrors the bash ``phase_label`` helper at
    ``hooks/cortex-scan-lifecycle.sh`` lines 204-218. Pure function: no
    I/O, no side effects. Consumed by the ``additionalContext`` emitter
    to produce strings like ``"Phase: Implement (3/5 tasks done)"``.

    Mapping rules:

    * ``"research"``                  -> ``"Research"``
    * ``"specify"``                   -> ``"Specify"``
    * ``"plan"``                      -> ``"Plan"``
    * ``"implement:<x>/<y>"``         -> ``"Implement (<x>/<y> tasks done)"``
    * ``"implement-rework:<n>"``      -> ``"Implement — rework (review cycle <n>)"``
    * ``"review"``                    -> ``"Review"``
    * ``"escalated"``                 -> ``"Escalated (REJECTED — needs user direction)"``
    * ``"complete:awaiting-merge"``   -> ``"Complete (awaiting merge)"``
    * ``"complete"``                  -> ``"Complete"``
    * any other phase                 -> the encoded phase string verbatim

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by :func:`_encode_phase`.

    Returns
    -------
    str
        The human-readable phase label.
    """

    if encoded_phase == "research":
        return "Research"
    if encoded_phase == "specify":
        return "Specify"
    if encoded_phase == "plan":
        return "Plan"
    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        return f"Implement ({progress} tasks done)"
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return f"Implement — rework (review cycle {cycle})"
    if encoded_phase == "review":
        return "Review"
    if encoded_phase == "escalated":
        return "Escalated (REJECTED — needs user direction)"
    if encoded_phase == "complete:awaiting-merge":
        return "Complete (awaiting merge)"
    if encoded_phase == "complete":
        return "Complete"
    return encoded_phase


def _interrupted_hint(encoded_phase: str, active_feature: str) -> str:
    """Return a one-line interrupted-state hint, or empty when not applicable.

    Mirrors the bash interrupted-state hint emission at
    ``hooks/cortex-scan-lifecycle.sh`` lines 378-398. Pure function: no
    I/O, no side effects. The caller appends the returned hint to the
    ``additionalContext`` block on its own line; an empty string signals
    "no hint applicable" (no extra line should be emitted).

    Hint rules:

    * ``"implement:<checked>/<total>"`` with ``0 < checked < total``
      -> "Interrupted: implementation in progress ..." hint.
    * ``"implement:<checked>/<total>"`` with ``checked == 0`` or
      ``checked >= total`` -> empty (not-started or fully-done).
    * ``"implement-rework:<cycle>"`` -> "Interrupted: review cycle ..." hint.
    * ``"escalated"`` -> "Action needed: review returned REJECTED ..." hint.
    * any other phase -> empty.

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by :func:`_encode_phase`.
    active_feature:
        Feature slug of the active lifecycle, used to render the
        ``/cortex-core:lifecycle <feature>`` resume command and the
        ``cortex/lifecycle/<feature>/review.md`` artifact path.

    Returns
    -------
    str
        The hint line (no trailing newline), or an empty string when no
        interrupted-state hint applies.
    """

    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        if "/" not in progress:
            return ""
        checked_str, _, total_str = progress.partition("/")
        try:
            checked = int(checked_str)
            total = int(total_str)
        except ValueError:
            return ""
        if checked > 0 and checked < total:
            return (
                f"Interrupted: implementation in progress "
                f"({checked} of {total} tasks done). "
                f"Resume with /cortex-core:lifecycle {active_feature}."
            )
        return ""
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return (
            f"Interrupted: review cycle {cycle} returned CHANGES_REQUESTED. "
            f"Re-enter implementation to address feedback. "
            f"Resume with /cortex-core:lifecycle {active_feature}."
        )
    if encoded_phase == "escalated":
        return (
            f"Action needed: review returned REJECTED. See "
            f"cortex/lifecycle/{active_feature}/review.md for analysis."
        )
    return ""


def _events_log_has_event(events_log: Path, event_name: str) -> bool:
    """Return ``True`` if ``events_log`` contains ``"event": "<event_name>"``.

    Mirrors the bash hook's ``grep -q '"event"[[:space:]]*:[[:space:]]*"X"'``
    test used to detect the ``pr_opened`` / ``feature_complete`` /
    ``feature_wontfix`` events when promoting ``complete`` to
    ``complete:awaiting-merge`` (bash precedent lines 311-321). Returns
    ``False`` for missing/unreadable files (bash ``2>/dev/null`` swallow).
    """

    try:
        content = events_log.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    # Match ``"event"`` followed by any whitespace, colon, any whitespace,
    # then the quoted event name. We don't need a regex here: the bash
    # hook's grep uses ``[[:space:]]*`` which is permissive — we look for
    # the simplest canonical form first and then the spaced variants.
    # In practice events.log is JSONL with no extra whitespace, so the
    # tight form covers production.
    needle_tight = f'"event": "{event_name}"'
    if needle_tight in content:
        return True
    needle_no_space = f'"event":"{event_name}"'
    return needle_no_space in content


def _metrics_summary_line(metrics_file: Path) -> str | None:
    """Build the metrics-summary line from ``metrics.json``.

    Mirrors bash precedent lines 443-469. Returns ``None`` when the
    metrics file is absent or unparseable; otherwise returns the
    single-line summary string the orchestrator appends to the context.

    The shape is:
    ``"Metrics: N completed features | Simple: avg X tasks, Y rework | Complex: avg X tasks, Y rework"``

    where ``N`` is ``len(features)`` and the avg fields default to ``0``
    when missing (bash ``// 0`` fallback). Numbers are formatted in
    their natural JSON form (no rounding) — bash echoes whatever ``jq``
    produces, which for integer ``0`` is ``"0"`` and for floats is the
    canonical ``json``-decoder repr.
    """

    if not metrics_file.is_file():
        return None
    try:
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    features = data.get("features")
    completed = len(features) if isinstance(features, dict) else 0

    aggregates = data.get("aggregates") or {}
    if not isinstance(aggregates, dict):
        aggregates = {}
    simple = aggregates.get("simple") or {}
    if not isinstance(simple, dict):
        simple = {}
    complex_ = aggregates.get("complex") or {}
    if not isinstance(complex_, dict):
        complex_ = {}

    def _fmt(val: object) -> str:
        # Mirror the bash output: jq emits the raw JSON form. ``json.dumps``
        # of an int gives "3"; of a float gives "3.5" / "0.0". The bash
        # hook's `// 0` fallback emits "0" for missing.
        if val is None:
            return "0"
        if isinstance(val, bool):
            # Defensive: bools are ints in Python; bash never emits bool here.
            return "0"
        if isinstance(val, (int, float)):
            return json.dumps(val)
        return str(val)

    m_simple_tasks = _fmt(simple.get("avg_task_count", 0))
    m_simple_rework = _fmt(simple.get("avg_rework_cycles", 0))
    m_complex_tasks = _fmt(complex_.get("avg_task_count", 0))
    m_complex_rework = _fmt(complex_.get("avg_rework_cycles", 0))

    return (
        f"Metrics: {completed} completed features | "
        f"Simple: avg {m_simple_tasks} tasks, {m_simple_rework} rework | "
        f"Complex: avg {m_complex_tasks} tasks, {m_complex_rework} rework"
    )


def _build_additional_context(
    pipeline_state: "PipelineState",
    active_feature: str,
    active_phase: str,
    incomplete: list[tuple[str, str]],
    lifecycle_dir: Path,
    metrics_summary: str | None = None,
) -> str:
    """Assemble the SessionStart ``additionalContext`` payload.

    Mirrors the bash precedent at lines 368-435 (active-feature header,
    phase line, interrupted hints, other-incomplete enumeration,
    multi-incomplete prompt fallback) and 426-435 (pipeline-context
    prepend) and 471-476 (metrics-summary append). Pure-ish: only the
    interrupted-hint helpers and the phase-label helper are called; no
    I/O beyond what those helpers perform (none).

    Parameters
    ----------
    pipeline_state:
        Pipeline state produced by
        :func:`cortex_command.hooks._pipeline_state.PipelineState.from_path`.
        Its ``context_string`` is prepended when non-empty.
    active_feature:
        Slug of the active feature (empty string when no active feature
        was determined — caller falls through to the multi-incomplete
        prompt branch when ``len(incomplete) > 1``).
    active_phase:
        Encoded phase string for the active feature (empty when no
        active feature). Consumed by :func:`_phase_label` and
        :func:`_interrupted_hint`.
    incomplete:
        Ordered list of ``(feature_slug, encoded_phase)`` pairs for
        every incomplete feature. The active feature is included here
        too; the helper skips it when enumerating "other incomplete
        lifecycles."
    lifecycle_dir:
        ``cortex/lifecycle/`` path. Currently unused by the assembler
        itself (path-derived artifact lines are constant text), but
        exposed for forward compatibility with the orchestrator's
        verification harness.
    metrics_summary:
        Optional metrics-summary line (already built by
        :func:`_metrics_summary_line`). Appended on its own line when
        non-``None`` AND an ``active_feature`` was determined (bash
        gates the metrics append on ``active_feature`` at line 439).

    Returns
    -------
    str
        The complete ``additionalContext`` string ready for the
        ``hookSpecificOutput`` envelope. Empty string signals "no
        context to inject" (caller suppresses the JSON output).
    """

    del lifecycle_dir  # Reserved for future use; bash uses constant text.

    context = ""

    if active_feature:
        label = _phase_label(active_phase)
        context = (
            f"Active lifecycle: {active_feature} | Phase: {label}\n"
            f"Artifacts: cortex/lifecycle/{active_feature}/"
        )

        hint = _interrupted_hint(active_phase, active_feature)
        if hint:
            context = f"{context}\n{hint}"

        # Note other incomplete features if any (bash lines 401-412).
        others = [
            (slug, phase)
            for slug, phase in incomplete
            if slug != active_feature
        ]
        if others:
            context = f"{context}\nOther incomplete lifecycles:"
            for slug, phase in others:
                other_label = _phase_label(phase)
                context = f"{context}\n  - {slug} ({other_label})"
            context = (
                f"{context}\nSwitch with /cortex-core:lifecycle resume "
                f"<feature>."
            )

    elif len(incomplete) > 1:
        # Multiple incomplete, no session match (bash lines 414-424).
        context = "Multiple incomplete lifecycles — select one to resume:"
        for slug, phase in incomplete:
            other_label = _phase_label(phase)
            context = f"{context}\n  - {slug} ({other_label})"
        context = (
            f"{context}\nResume with /cortex-core:lifecycle resume <feature>."
        )

    # Prepend pipeline context (bash lines 428-435).
    pipeline_ctx = pipeline_state.context_string
    if pipeline_ctx:
        if context:
            context = f"{pipeline_ctx}\n{context}"
        else:
            context = pipeline_ctx

    # Append metrics summary (bash lines 471-476). Bash gates on
    # ``active_feature`` being non-empty.
    if metrics_summary and active_feature:
        if context:
            context = f"{context}\n{metrics_summary}"
        else:
            context = metrics_summary

    return context


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``cortex hooks scan-lifecycle``.

    Reads a SessionStart hook JSON payload on stdin, parses
    ``session_id`` and ``cwd``, and (in the completed implementation)
    emits a ``hookSpecificOutput`` block on stdout that injects
    lifecycle context for the active feature.

    Parameters
    ----------
    argv:
        Optional command-line argument list. Reserved for future use;
        the skeleton currently ignores it.

    Returns
    -------
    int
        Process exit code. ``0`` indicates the hook ran successfully
        (whether or not it emitted context); nonzero is reserved for
        genuine internal errors per the spec.
    """

    del argv  # Reserved for future use.

    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0

    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    if not isinstance(payload, dict):
        return 0

    session_id_raw = payload.get("session_id") or ""
    if not isinstance(session_id_raw, str):
        session_id_raw = ""
    session_id = session_id_raw

    cwd_raw = payload.get("cwd")
    if not isinstance(cwd_raw, str) or not cwd_raw:
        cwd_raw = os.getcwd()
    cwd = Path(cwd_raw)

    # --- Session identity injection (bash precedent lines 7-13) ---
    # Emit before the cwd/lifecycle early-exit so non-cortex sessions still
    # propagate LIFECYCLE_SESSION_ID for downstream hook invocations.
    if session_id:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            export_line = (
                f"export LIFECYCLE_SESSION_ID={shlex.quote(session_id)}\n"
            )
            try:
                with open(env_file, "a", encoding="utf-8") as fh:
                    fh.write(export_line)
            except OSError:
                # Best-effort: parity with bash, which would surface a
                # redirection failure but not abort the hook chain.
                pass
        else:
            print(
                "[scan-lifecycle] CLAUDE_ENV_FILE not set; "
                "cannot inject LIFECYCLE_SESSION_ID",
                file=sys.stderr,
            )

    # --- cwd/lifecycle early-exit (bash precedent lines 26-29) ---
    # Non-cortex repos: silently exit 0 with no stdout. The wrapper at
    # hooks/cortex-scan-lifecycle.sh does its own pre-check; this is
    # defense-in-depth for the direct-invocation path.
    lifecycle_dir = cwd / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return 0

    # Lazy-imports per the module docstring's discipline. Keeping these
    # inside ``main`` means ``cortex hooks scan-lifecycle --help`` and
    # the cwd-early-exit path do not pay the package-import cost.
    from cortex_command.common import detect_lifecycle_phase
    from cortex_command.hooks._pipeline_state import PipelineState
    from cortex_command.hooks._session_state import (
        claim_single_feature,
        migrate_session_p1,
        migrate_session_p2,
        skip_orphan_session_owner,
    )

    # --- Session migration (bash precedent lines 39-73) ---
    # Survives /clear: when SESSION_ID (fresh) != LIFECYCLE_SESSION_ID
    # (stale) and both are non-empty, migrate .session files so the
    # active feature is still matched after /clear.
    lifecycle_session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")
    if (
        session_id
        and lifecycle_session_id
        and session_id != lifecycle_session_id
    ):
        # Phase 1: scan .session files for the stale id.
        migration_done = False
        try:
            children = sorted(lifecycle_dir.iterdir())
        except OSError:
            children = []
        for child in children:
            if not child.is_dir():
                continue
            if (child / ".session").is_file():
                if migrate_session_p1(
                    child, session_id, lifecycle_session_id
                ):
                    migration_done = True

        # Phase 2: chain migration via .session-owner. Skip features
        # whose ``.session-owner`` is orphaned (no ``.session`` AND no
        # incomplete-phase indicator i.e. complete) — bash resurrects
        # those; the Python port intentionally diverges.
        if not migration_done:
            # Pre-filter: don't enter P2 for orphan features that are
            # complete. The orchestrator inspects each feature's phase
            # AFTER candidate-collection below, but the orphan check
            # here is cheap (file presence) — let _session_state do the
            # heavy lifting via its own loop, and we filter post-hoc by
            # phase detection.
            written = migrate_session_p2(
                lifecycle_dir, session_id, lifecycle_session_id
            )
            # OR-branch enforcement: if a feature directory had only
            # ``.session-owner`` (no ``.session``) AND its detected
            # phase is "complete", undo any write the P2 helper made.
            # (The helper writes unconditionally; bash's OR-resurrection
            # is the bug we're avoiding — see spec req #6 branch OR.)
            for feature_dir in written:
                phase_info = detect_lifecycle_phase(feature_dir)
                phase_name = phase_info.get("phase")
                if phase_name == "complete":
                    # The feature was complete and only had an orphan
                    # .session-owner; bash would have resurrected
                    # .session here, but we treat that as a latent bug.
                    # Remove the .session we just wrote.
                    try:
                        (feature_dir / ".session").unlink()
                    except OSError:
                        pass
            # Belt-and-suspenders: also expose the orphan detector for
            # any future P2 caller that wants pre-write gating.
            _ = skip_orphan_session_owner  # Symbol kept reachable.

    # --- Pipeline-state detection (bash precedent lines 75-171) ---
    pipeline_state = PipelineState.from_path(
        lifecycle_dir / "overnight-state.json"
    )

    # --- Scan candidate feature directories (bash precedent lines 220-244) ---
    candidate_dirs: list[Path] = []
    candidate_features: list[str] = []
    try:
        children = sorted(lifecycle_dir.iterdir())
    except OSError:
        children = []
    for child in children:
        if not child.is_dir():
            continue
        feature = child.name
        if feature == "archive":
            continue
        # Suppress Morning Review batch features.
        if pipeline_state.morning_review_active and (
            feature in pipeline_state.morning_review_features
        ):
            continue
        candidate_dirs.append(child)
        candidate_features.append(feature)

    # --- Phase detection per candidate (bash precedent lines 249-326) ---
    incomplete: list[tuple[str, str]] = []
    for feature_dir, feature in zip(candidate_dirs, candidate_features):
        try:
            r = detect_lifecycle_phase(feature_dir)
        except Exception:
            continue
        phase = str(r.get("phase", "") or "")
        if not phase:
            continue
        try:
            checked = int(r.get("checked", 0) or 0)
        except (TypeError, ValueError):
            checked = 0
        try:
            total = int(r.get("total", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        try:
            cycle = int(r.get("cycle", 1) or 1)
        except (TypeError, ValueError):
            cycle = 1

        encoded = _encode_phase(phase, checked, total, cycle)

        # Promote "complete" to "complete:awaiting-merge" when
        # ``pr_opened`` event is present and neither ``feature_complete``
        # nor ``feature_wontfix`` are. Otherwise filter complete features
        # out of the incomplete list. (Bash precedent lines 311-321.)
        if encoded == "complete":
            events_log = feature_dir / "events.log"
            if (
                _events_log_has_event(events_log, "pr_opened")
                and not _events_log_has_event(
                    events_log, "feature_complete"
                )
                and not _events_log_has_event(
                    events_log, "feature_wontfix"
                )
            ):
                encoded = "complete:awaiting-merge"
            else:
                continue

        incomplete.append((feature, encoded))

    # No incomplete features and no pipeline context — nothing to inject.
    if not incomplete and not pipeline_state.context_string:
        return 0

    # --- Determine active feature (bash precedent lines 333-366) ---
    # Order:
    #   (1) session-id match against ``.session`` files,
    #   (2) crash-recovery claim if exactly one incomplete,
    #   (3) no match → multi-incomplete prompt (handled in builder).
    active_feature = ""
    active_phase = ""

    if session_id:
        for feature, encoded in incomplete:
            session_file = lifecycle_dir / feature / ".session"
            if not session_file.is_file():
                continue
            try:
                file_id = "".join(
                    session_file.read_text(encoding="utf-8").split()
                )
            except (OSError, ValueError):
                continue
            if file_id == session_id:
                active_feature = feature
                active_phase = encoded
                break

    if not active_feature and len(incomplete) == 1:
        active_feature, active_phase = incomplete[0]
        if session_id:
            # Crash-recovery claim under flock (bash precedent line 364
            # was a bare ``echo``; the Python port serializes via
            # _session_state.claim_single_feature).
            try:
                claim_single_feature(
                    lifecycle_dir / active_feature, session_id
                )
            except OSError:
                # Best-effort: parity with bash's redirect, which
                # would surface stderr but not abort.
                pass

    # --- Regenerate metrics (bash precedent lines 437-440) ---
    # Replace the bash subprocess call to ``cortex-pipeline-metrics``
    # with a direct module-function call. Suppress stdout (which the
    # bash hook discards via ``>/dev/null 2>&1``) so the SessionStart
    # JSON envelope stays the only thing on our stdout.
    metrics_summary: str | None = None
    if active_feature:
        try:
            from cortex_command.pipeline import metrics as metrics_mod
        except ImportError:
            metrics_mod = None  # type: ignore[assignment]
        if metrics_mod is not None:
            try:
                with contextlib.redirect_stdout(
                    io.StringIO()
                ), contextlib.redirect_stderr(io.StringIO()):
                    metrics_mod.main(["--root", str(cwd)])
            except SystemExit:
                # argparse may raise SystemExit on --help; we don't pass
                # --help, but defensive.
                pass
            except Exception:
                # Bash uses ``|| true`` after the metrics regen — never
                # fail the hook because the metrics pass had a problem.
                pass
        metrics_file = lifecycle_dir / "metrics.json"
        metrics_summary = _metrics_summary_line(metrics_file)

    # --- Build final additionalContext ---
    context = _build_additional_context(
        pipeline_state,
        active_feature,
        active_phase,
        incomplete,
        lifecycle_dir,
        metrics_summary=metrics_summary,
    )

    if context:
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }
        sys.stdout.write(json.dumps(envelope, indent=2) + "\n")

    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI entry shim
    sys.exit(main(sys.argv[1:]))
