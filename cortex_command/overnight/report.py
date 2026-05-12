"""Morning report generator for overnight orchestration sessions.

Reads overnight state, event logs, deferral files, and batch results
to produce a morning report with executive summary, completed features,
deferred questions, failed features, action checklist, and run
statistics.  The report is written to the session directory at
``lifecycle/sessions/{session-id}/morning-report.md``.
"""

from __future__ import annotations

import glob as glob_mod
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid as uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cortex_command.common import _resolve_user_project_root, atomic_write, read_tier, slugify

from cortex_command.overnight.deferral import (
    DEFAULT_DEFERRED_DIR,
    SEVERITY_BLOCKING,
    SEVERITY_INFORMATIONAL,
    SEVERITY_NON_BLOCKING,
    DeferralQuestion,
    read_deferrals,
)
from cortex_command.overnight.events import _default_log_path, read_events
from cortex_command.overnight import fail_markers as fail_markers_module
from cortex_command.overnight.fail_markers import FailedFire
from cortex_command.overnight.state import OvernightState, _default_state_path, load_state, session_dir


# ---------------------------------------------------------------------------
# Report data collection
# ---------------------------------------------------------------------------


def _default_report_path() -> Path:
    """Resolve the default morning-report.md path at call time.

    Spec R3c forbids module-level capture of `_resolve_user_project_root()`;
    every consumer must invoke this function (or supply an explicit path).
    """
    return _resolve_user_project_root() / "cortex/lifecycle" / "morning-report.md"


@dataclass
class NewBacklogItem:
    """Represents a backlog item created automatically after an overnight run."""

    id: int
    title: str
    type: str
    reason: str
    filename: str


@dataclass
class ReportData:
    """Aggregated data from all overnight sources for report rendering.

    Fields:
        session_id: Unique session identifier.
        date: Date string (YYYY-MM-DD).
        state: Loaded OvernightState.
        events: Parsed event log entries.
        deferrals: Parsed DeferralQuestion instances.
        batch_results: Parsed batch result dicts from JSON files.
        round_history: Round summaries from state.
        tool_failures: Per-tool failure data from the session's /tmp dir.
            Maps tool name to {"count": int, "last_exit_code": str}.
        pr_urls: PR URLs keyed by os.path.realpath(repo_path).
            Populated from the temp JSON file written by runner.sh.
    """

    session_id: str = ""
    date: str = ""
    state: Optional[OvernightState] = None
    events: list[dict[str, Any]] = field(default_factory=list)
    deferrals: list[DeferralQuestion] = field(default_factory=list)
    batch_results: list[dict[str, Any]] = field(default_factory=list)
    round_history: list = field(default_factory=list)
    pipeline_events_path: Optional[Path] = None
    new_backlog_items: list[NewBacklogItem] = field(default_factory=list)
    tool_failures: dict[str, dict] = field(default_factory=dict)
    pr_urls: dict[str, str] = field(default_factory=dict)
    scheduled_fire_failures: list[FailedFire] = field(default_factory=list)
    sandbox_denials: dict[str, int] = field(default_factory=dict)


def collect_report_data(
    state_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
    results_dir: Optional[Path] = None,
    pipeline_events_path: Optional[Path] = None,
) -> ReportData:
    """Collect all data sources needed for the morning report.

    Args:
        state_path: Path to overnight-state.json. Defaults to
            ``_default_state_path()`` resolved at call time.
        events_path: Path to overnight-events.log. Defaults to
            ``_default_log_path()`` resolved at call time.
        deferred_dir: Directory containing deferral markdown files.
        results_dir: Directory containing batch-*-results.json files.
            When None, resolved from session_id via session_dir().
        pipeline_events_path: Path to pipeline-events.log for worker
            output extraction.  When None, resolved from session_id
            via session_dir().

    Returns:
        ReportData with all fields populated from available sources.
    """
    state_path = state_path or _default_state_path()
    events_path = events_path or _default_log_path()
    lifecycle_root = _resolve_user_project_root() / "cortex/lifecycle"
    data = ReportData()

    # Load state
    if state_path.exists():
        state = load_state(state_path)
        data.state = state
        data.session_id = state.session_id
        data.round_history = list(state.round_history)

    # Resolve results_dir from session_id when not provided
    if results_dir is None:
        if data.session_id:
            sdir = session_dir(data.session_id, lifecycle_root=lifecycle_root)
            if sdir.is_dir():
                results_dir = sdir
            else:
                print(
                    f"warning: session dir {sdir} does not exist; "
                    f"skipping batch results",
                    file=sys.stderr,
                )
        else:
            print(
                "warning: no session_id in state; skipping batch results",
                file=sys.stderr,
            )

    # Resolve pipeline_events_path from session_id when not provided
    if pipeline_events_path is None:
        if data.session_id:
            sdir = session_dir(data.session_id, lifecycle_root=lifecycle_root)
            candidate = sdir / "pipeline-events.log"
            if candidate.exists():
                pipeline_events_path = candidate
            elif sdir.is_dir():
                # Dir exists but pipeline-events.log is absent — not an error
                pipeline_events_path = candidate
            else:
                print(
                    f"warning: session dir {sdir} does not exist; "
                    f"skipping pipeline events",
                    file=sys.stderr,
                )
        else:
            print(
                "warning: no session_id in state; skipping pipeline events",
                file=sys.stderr,
            )

    data.pipeline_events_path = pipeline_events_path

    # Load events
    data.events = read_events(events_path)

    # Load deferrals
    data.deferrals = read_deferrals(deferred_dir)

    # Load batch results
    if results_dir is not None:
        pattern = str(results_dir / "batch-*-results.json")
        for result_path in sorted(glob_mod.glob(pattern)):
            try:
                raw = json.loads(Path(result_path).read_text(encoding="utf-8"))
                data.batch_results.append(raw)
            except (json.JSONDecodeError, OSError):
                pass

    # Determine date
    if data.events:
        first_ts = data.events[0].get("ts", "")
        data.date = first_ts[:10] if len(first_ts) >= 10 else _today()
    else:
        data.date = _today()

    # Collect tool failures from the session-scoped /tmp dir
    if data.session_id:
        data.tool_failures = collect_tool_failures(data.session_id)
        data.sandbox_denials = collect_sandbox_denials(data.session_id)
    else:
        # Fall back to today's date-based key (mirrors the hook's fallback)
        date_key = f"date-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        data.tool_failures = collect_tool_failures(date_key)
        data.sandbox_denials = collect_sandbox_denials(date_key)

    # Scan sibling session dirs for scheduled-fire-failed.json markers
    # written by the launchd-fired launcher script when fire-time spawn
    # fails (Task 3, spec §R13). The morning report surfaces these in a
    # dedicated section so TCC denials and missing-binary failures don't
    # hide behind the macOS notification alone.
    data.scheduled_fire_failures = fail_markers_module.scan_session_dirs(
        lifecycle_root,
    )

    return data


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def create_followup_backlog_items(
    data: ReportData,
    backlog_dir: Path,
) -> list[NewBacklogItem]:
    """Create backlog items for failed, paused, and deferred features.

    For each failed/paused feature writes a chore-type backlog item; for each
    deferred feature writes a feature-type backlog item. Tags are inherited
    from the source feature's existing backlog item.

    Args:
        data: Aggregated report data.
        backlog_dir: Directory to write new backlog files into. Required —
            callers must route explicitly through the session's worktree.

    Returns:
        List of NewBacklogItem descriptors for each file written.
    """
    if data.state is None:
        return []

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")

    backlog_dir.mkdir(parents=True, exist_ok=True)
    result: list[NewBacklogItem] = []
    today = _today()

    for name, fs in sorted(data.state.features.items()):
        if fs.status not in ("failed", "paused", "deferred"):
            continue

        item_id = _next_backlog_id(backlog_dir)
        slug = name  # feature names already use kebab-case
        tags = _find_backlog_tags(name, backlog_dir)
        tags_str = ", ".join(tags) if tags else ""

        if fs.status in ("failed", "paused"):
            title = f"Follow up: {name}"
            item_type = "chore"
            reason = "failed"
            error_summary = fs.error or "unknown error"
            body = (
                f"Feature **{name}** failed during the overnight run. "
                f"Error: {error_summary}. "
                f"Review `lifecycle/{name}/learnings/progress.txt` and retry or investigate."
            )
        else:  # deferred
            title = f"Retry deferred: {name}"
            item_type = "feature"
            reason = "deferred"
            # Count deferral questions
            q_count = sum(1 for dq in data.deferrals if dq.feature == name)
            if q_count == 0:
                q_count = len(glob_mod.glob(f"deferred/{name}-q*.md"))
            body = (
                f"Feature **{name}** was deferred during the overnight run with "
                f"{q_count} unanswered question{'s' if q_count != 1 else ''}. "
                f"See `deferred/{name}-q*.md` for details."
            )

        item_uuid = str(uuid_mod.uuid4())
        lifecycle_slug = name  # Use original feature slug, not slugify("Follow up: ...")
        frontmatter = (
            "---\n"
            f"title: {title}\n"
            f"status: backlog\n"
            f"priority: medium\n"
            f"type: {item_type}\n"
            f"tags: [{tags_str}]\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            f"blocks: []\n"
            f"blocked-by: []\n"
            f"schema_version: \"1\"\n"
            f"uuid: {item_uuid}\n"
            f"lifecycle_slug: {lifecycle_slug}\n"
            f"session_id: {session_id}\n"
            "---\n"
        )
        content = frontmatter + "\n" + body + "\n"
        filename = f"{item_id:03d}-{slug}.md"
        atomic_write(backlog_dir / filename, content)

        result.append(NewBacklogItem(
            id=item_id,
            title=title,
            type=item_type,
            reason=reason,
            filename=filename,
        ))

    return result


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_soft_fail_header(data: ReportData) -> str:
    """Render the unconditional CORTEX_SANDBOX_SOFT_FAIL header (spec Req 20).

    Scans ``data.events`` for any ``sandbox_soft_fail_active`` entry recorded
    by the per-spawn settings builder when ``CORTEX_SANDBOX_SOFT_FAIL=1`` was
    truthy at orchestrator-spawn or per-dispatch construction time. Returns
    a one-line header string when at least one such event is present, or
    the empty string otherwise so the caller can omit the section cleanly.

    The header makes operators aware that sandbox enforcement was downgraded
    for the session so they can correlate any unexpected commits-on-main
    with the kill-switch state.
    """
    for evt in data.events:
        if evt.get("event") == "sandbox_soft_fail_active":
            return (
                "CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; "
                "sandbox.failIfUnavailable was downgraded to false."
            )
    return ""


def render_executive_summary(data: ReportData) -> str:
    """Render the executive summary section."""
    lines: list[str] = ["## Executive Summary", ""]

    if data.state is None:
        lines.append("No overnight state found.")
        return "\n".join(lines)

    features = data.state.features
    total = len(features)
    merged = sum(1 for f in features.values() if f.status == "merged")
    deferred = sum(1 for f in features.values() if f.status == "deferred")
    failed = sum(1 for f in features.values() if f.status in ("failed", "paused"))

    # Circuit breaker check
    cb_fired = any(
        br.get("circuit_breaker_fired", False)
        for br in data.batch_results
    )

    # Cross-check state verdict against batch results to detect discrepancies
    # (e.g. concurrent runners where state says "merged" but batch says "paused")
    batch_merged_names: set[str] = set()
    batch_paused_names: set[str] = set()
    for br in data.batch_results:
        for name in br.get("features_merged", []):
            batch_merged_names.add(name)
        for fp in br.get("features_paused", []):
            batch_paused_names.add(fp["name"] if isinstance(fp, dict) else str(fp))
    state_merged_names = {name for name, fs in features.items() if fs.status == "merged"}
    # Features the state considers merged but batch never recorded a successful merge for
    state_batch_conflicts = state_merged_names - batch_merged_names

    # Verdict
    if merged == total:
        verdict = "Clean run"
    elif deferred > 0 and failed == 0:
        verdict = "Needs attention"
    else:
        verdict = "Significant issues"

    if cb_fired:
        verdict = "Significant issues"

    # Duration
    duration_str = _compute_duration(data.events)

    # Rounds — prefer state (authoritative) over events log (may be inflated
    # by concurrent runners each writing their own round events).
    rounds = len(data.round_history) or max(data.state.current_round - 1, 0)
    if rounds == 0:
        rounds = _count_round_events(data.events)

    lines.append(f"**Verdict**: {verdict}")
    lines.append(f"- Features completed: {merged}/{total}")
    lines.append(f"- Features deferred: {deferred} (questions need answers)")
    lines.append(f"- Features failed: {failed} (paused, need investigation)")
    lines.append(f"- Rounds completed: {rounds}")
    lines.append(f"- Duration: {duration_str}")
    if state_batch_conflicts:
        lines.append(
            f"- **Warning**: {len(state_batch_conflicts)} feature(s) show 'merged' in state "
            f"but have no merge recorded in batch results — possible concurrent runner "
            f"or state/batch mismatch: {', '.join(sorted(state_batch_conflicts))}"
        )
    if getattr(data.state, "paused_reason", None) == "budget_exhausted":
        lines.append(
            "> **Session paused: API budget exhausted.** Features in `pending` status "
            "will resume on `/overnight resume`."
        )
        lines.append("")
    elif getattr(data.state, "paused_reason", None) == "api_rate_limit":
        lines.append(
            "> **Session paused: API rate limit hit.** Features in `pending` status "
            "remain queued for resume; consult `pipeline-events.log` for retry context."
        )
        lines.append("")
    lines.append("")

    return "\n".join(lines)


def _compute_duration(events: list[dict]) -> str:
    """Compute duration from first to last event timestamp."""
    if not events:
        return "unknown"

    first_ts = events[0].get("ts", "")
    last_ts = events[-1].get("ts", "")

    try:
        start = datetime.fromisoformat(first_ts)
        end = datetime.fromisoformat(last_ts)
        delta = end - start
        total_minutes = int(delta.total_seconds() / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h {minutes}m"
    except (ValueError, TypeError):
        return "unknown"


def _count_round_events(events: list[dict]) -> int:
    """Count ROUND_COMPLETE events."""
    return sum(1 for e in events if e.get("event") == "round_complete")


def render_completed_features(data: ReportData) -> str:
    """Render the completed features section grouped by repo.

    Features are grouped under level-3 subheadings by repo name.
    Machine-config features (repo_path is None) appear first under the
    repo root's directory name; cross-repo features appear alphabetically
    by repo name with their PR URL if available.
    """
    lines: list[str] = ["## Completed Features", ""]

    if data.state is None:
        lines.append("No overnight state found.")
        return "\n".join(lines)

    # Determine home repo name for the home repo group.
    # Prefer the first key of integration_branches (the home repo path) so that
    # non-home-repo sessions label the group correctly.  Fall back to
    # deriving the name from this file's location when integration_branches is
    # empty (e.g. legacy state files).
    if data.state.integration_branches:
        home_repo_name = Path(next(iter(data.state.integration_branches))).name
    else:
        home_repo_name = _resolve_user_project_root().name

    # Build groups: Optional[repo_path] -> list[feature_name]
    groups: dict[Optional[str], list[str]] = {}
    for name, fs in data.state.features.items():
        if fs.status != "merged":
            continue
        key = fs.repo_path  # raw value, may be None
        if key not in groups:
            groups[key] = []
        groups[key].append(name)

    if not groups:
        lines.append("No features completed in this run.")
        lines.append("")
        return "\n".join(lines)

    # Sort: home repo (None) first, then cross-repo alphabetically by name
    sorted_keys: list[Optional[str]] = []
    if None in groups:
        sorted_keys.append(None)
    cross_repo_keys = sorted(
        (k for k in groups if k is not None),
        key=lambda k: Path(k).name,
    )
    sorted_keys.extend(cross_repo_keys)

    # Collect key_files_changed from batch results
    files_by_feature: dict[str, list[str]] = {}
    for br in data.batch_results:
        for feat, files in br.get("key_files_changed", {}).items():
            files_by_feature[feat] = files

    def _render_feature_block(name: str) -> None:
        backlog_id = _find_backlog_id(name)
        header = f"#### {name}"
        if backlog_id:
            header += f" (backlog #{backlog_id:03d})"
        lines.append(header)
        lines.append("")

        # Key files changed
        changed = files_by_feature.get(name, [])
        lines.append("**Key files changed:**")
        if changed:
            for f in changed:
                lines.append(f"- {f}")
        else:
            lines.append("- (file list not available)")
        lines.append("")

        # Cost
        if data.pipeline_events_path is not None:
            cost = _aggregate_feature_cost(name, data.pipeline_events_path)
            if cost is not None:
                lines.append(f"**Cost**: ${cost:.2f}")
                lines.append("")

        # How to try — tier-conditional verification source with fallback chain
        # (R13d/R13e compat shim: new-shape readers win when both shapes present).
        tier = read_tier(name)
        if tier == "complex":
            verification = (
                _read_acceptance(name)
                or _read_last_phase_checkpoint(name)
                or _read_verification_strategy(name)
            )
        else:
            verification = (
                _read_last_phase_checkpoint(name)
                or _read_verification_strategy(name)
            )
        lines.append("**How to try:**")
        lines.append(verification if verification else "See feature plan for verification steps.")
        lines.append("")

        # Notes from learnings
        learnings = _read_learnings_summary(name)
        if learnings:
            lines.append("**Notes:**")
            lines.append(learnings)
            lines.append("")

        # Requirements drift
        drift = _read_requirements_drift(name)
        if drift is not None and drift["state"] == "detected":
            lines.append("**Requirements drift detected** — update required before next overnight:")
            for finding in drift["findings"]:
                lines.append(f"- {finding}")
            lines.append("")
        elif drift is not None and drift["state"] == "malformed":
            lines.append("**Requirements drift**: section is malformed and requires manual review.")
            lines.append("")

    for repo_path in sorted_keys:
        if repo_path is None:
            group_name = home_repo_name
        else:
            group_name = Path(repo_path).name

        lines.append(f"### {group_name}")
        lines.append("")

        # Append PR URL for cross-repo groups if available
        if repo_path is not None and data.pr_urls:
            normalized = os.path.realpath(repo_path)
            pr_url = next(
                (v for k, v in data.pr_urls.items() if os.path.realpath(k) == normalized),
                None,
            )
            if pr_url:
                lines.append(f"**PR**: {pr_url}")
                lines.append("")

        for name in groups[repo_path]:
            _render_feature_block(name)

    return "\n".join(lines)


def render_pending_drift(data: ReportData) -> str:
    """Render a Requirements Drift Flags section for non-completed features.

    Scans ``lifecycle/*/review.md`` for features that are NOT in the
    merged set (already rendered in the completed section) and NOT in a
    re-implementing state (stale review.md from a prior cycle).  For the
    remaining features, reads the Requirements Drift section and collects
    those with ``state == "detected"``.

    Returns an empty string when there are no pending drift flags, so the
    section is omitted entirely from the report.
    """
    # 1. Merged features — already rendered in the completed section
    merged: set[str] = set()
    if data.state is not None:
        for name, fs in data.state.features.items():
            if fs.status == "merged":
                merged.add(name)

    # 2. Re-implementing features — review.md is stale from a prior cycle
    reimplementing: set[str] = set()
    for review_path in sorted(Path("cortex/lifecycle").glob("*/review.md")):
        feature = review_path.parent.name
        events_path = Path(f"cortex/lifecycle/{feature}/events.log")
        if not events_path.exists():
            continue
        events = read_events(events_path)
        # Find most recent phase_transition event
        phase_transitions = [
            e for e in events if e.get("event") == "phase_transition"
        ]
        if phase_transitions and phase_transitions[-1].get("to") in {"implement", "implement-rework"}:
            reimplementing.add(feature)

    # 3. Scan cortex/lifecycle/*/review.md, skip merged and re-implementing
    drift_features: list[tuple[str, dict]] = []
    for review_path in sorted(Path("cortex/lifecycle").glob("*/review.md")):
        feature = review_path.parent.name
        if feature in merged or feature in reimplementing:
            continue
        drift = _read_requirements_drift(feature)
        if drift is not None and drift.get("state") == "detected":
            drift_features.append((feature, drift))

    # 4. No detected drift — omit the section entirely
    if not drift_features:
        return ""

    # 5. Render the section
    lines: list[str] = ["## Requirements Drift Flags", ""]
    for feature, drift in drift_features:
        lines.append(f"### {feature}")
        lines.append("")
        findings = drift.get("findings", [])
        if findings:
            for finding in findings:
                lines.append(f"- {finding}")
        else:
            lines.append("- (drift detected but no findings listed)")
        lines.append("")

    return "\n".join(lines)


def _next_backlog_id(backlog_dir: Path | str) -> int:
    """Return the next available backlog item ID.

    Scans both backlog_dir and backlog_dir/archive for files matching
    [0-9]*-*.md, finds the highest numeric prefix across both
    directories, and returns max + 1. Returns 1 if no files exist.
    """
    backlog_dir = Path(backlog_dir)
    ids: list[int] = []
    dirs_to_scan = [backlog_dir, backlog_dir / "archive"]
    _id_re = re.compile(r"^(\d+)-")
    for scan_dir in dirs_to_scan:
        if scan_dir.is_dir():
            for path in scan_dir.glob("[0-9]*-*.md"):
                m = _id_re.match(path.name)
                if m:
                    ids.append(int(m.group(1)))
    return max(ids) + 1 if ids else 1


def _find_backlog_tags(feature: str, backlog_dir: Path) -> list[str]:
    """Extract tags from the backlog item for a feature.

    Returns an empty list if the backlog file or tags field is not found.
    """
    if not backlog_dir.is_dir():
        return []

    # Mirror the broad-match logic from _find_backlog_id()
    matches = list(backlog_dir.glob(f"[0-9]*-*{feature}*.md"))
    if not matches:
        for path in backlog_dir.glob("[0-9]*-*.md"):
            if feature.replace("-", "") in path.name.replace("-", ""):
                matches = [path]
                break

    if not matches:
        return []

    text = matches[0].read_text(encoding="utf-8")
    m = re.search(r"^tags:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if not m:
        return []

    raw = m.group(1)
    return [t.strip() for t in raw.split(",") if t.strip()]


def _find_backlog_id(feature: str) -> Optional[int]:
    """Find the backlog item ID for a feature by scanning backlog/."""
    backlog_dir = Path("backlog")
    if not backlog_dir.is_dir():
        return None

    pattern = f"[0-9]*-*{feature}*.md"
    matches = list(backlog_dir.glob(pattern))
    _id_re = re.compile(r"^(\d+)-")
    if not matches:
        # Try a broader match
        for path in backlog_dir.glob("[0-9]*-*.md"):
            if feature.replace("-", "") in path.name.replace("-", ""):
                m = _id_re.match(path.name)
                if m:
                    return int(m.group(1))
        return None

    m = _id_re.match(matches[0].name)
    return int(m.group(1)) if m else None


def _read_verification_strategy(feature: str) -> str:
    """Read the verification strategy section from a feature's plan."""
    plan_path = Path(f"lifecycle/{feature}/plan.md")
    if not plan_path.exists():
        return ""

    text = plan_path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Verification Strategy\s*\n(.*?)(?=\n## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


def _read_acceptance(feature: str) -> str:
    """Read the ``## Acceptance`` section from a feature's plan."""
    plan_path = Path(f"lifecycle/{feature}/plan.md")
    if not plan_path.exists():
        return ""

    text = plan_path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Acceptance\s*\n(.*?)(?=\n## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


def _read_last_phase_checkpoint(feature: str) -> str:
    """Read the last populated ``**Checkpoint**:`` from ``## Outline``.

    Parses the ``## Outline`` section, locates the LAST ``### Phase N:``
    heading, and extracts that phase's ``**Checkpoint**:`` field value. If
    the last phase has the heading but no ``**Checkpoint**:`` field, walks
    backward through earlier phases and returns the most recent populated
    Checkpoint. Returns ``""`` when the plan has no ``## Outline`` section
    or when no phase in the Outline has a Checkpoint field.
    """
    plan_path = Path(f"lifecycle/{feature}/plan.md")
    if not plan_path.exists():
        return ""

    text = plan_path.read_text(encoding="utf-8")
    outline_match = re.search(
        r"^## Outline\s*\n(.*?)(?=\n## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not outline_match:
        return ""

    outline_body = outline_match.group(1)
    # Split outline body into phase blocks at each ### Phase N: heading.
    phase_pattern = re.compile(r"^### Phase \d+:.*$", re.MULTILINE)
    phase_starts = [m.start() for m in phase_pattern.finditer(outline_body)]
    if not phase_starts:
        return ""

    phase_blocks: list[str] = []
    for idx, start in enumerate(phase_starts):
        end = phase_starts[idx + 1] if idx + 1 < len(phase_starts) else len(outline_body)
        phase_blocks.append(outline_body[start:end])

    checkpoint_re = re.compile(
        r"^\*\*Checkpoint\*\*:\s*(.+?)(?=\n\*\*|\n###|\n##|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    # Walk backward through phases; return the most recent populated Checkpoint.
    for block in reversed(phase_blocks):
        cp_match = checkpoint_re.search(block)
        if cp_match:
            value = cp_match.group(1).strip()
            if value:
                return value
    return ""


def _read_requirements_drift(feature: str) -> dict | None:
    """Read the Requirements Drift section from a feature's review.md.

    Returns:
        None           – review.md absent or section not found.
        {"state": "malformed", "findings": []}  – section exists but no **State**: line.
        {"state": <value>, "findings": [<bullet strings>]}  – valid section.
    """
    review_path = Path(f"lifecycle/{feature}/review.md")
    if not review_path.exists():
        return None

    text = review_path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Requirements Drift\s*\n(.*?)(?=\n## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None

    body = match.group(1).strip()

    # Extract **State**: value
    state_match = re.search(r"\*\*State\*\*:\s*(.+)", body)
    if not state_match:
        return {"state": "malformed", "findings": []}

    state = state_match.group(1).strip()

    # Extract **Findings**: bullet lines
    findings: list[str] = []
    findings_match = re.search(
        r"\*\*Findings\*\*:\s*\n(.*?)(?=\n\*\*|\Z)",
        body,
        re.DOTALL,
    )
    if findings_match:
        for line in findings_match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                findings.append(line[2:].strip())

    return {"state": state, "findings": findings}


def _read_recovery_log_last_entry(feature: str) -> str:
    """Read recovery-log.md and return the last entry, truncated to 400 chars.

    Returns empty string when the file does not exist or contains no entries.
    Never raises — all I/O is wrapped in a try/except.
    """
    try:
        log_path = Path(f"lifecycle/{feature}/learnings/recovery-log.md")
        if not log_path.exists():
            return ""
        content = log_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        parts = content.split("## Recovery attempt ")
        last_entry = parts[-1].strip() if len(parts) > 1 else ""
        if not last_entry:
            return ""
        return ("## Recovery attempt " + last_entry)[:400]
    except Exception:
        return ""


def _read_learnings_summary(feature: str) -> str:
    """Read learnings and return a brief summary if any exist."""
    progress_path = Path(f"lifecycle/{feature}/learnings/progress.txt")
    if not progress_path.exists():
        return ""

    content = progress_path.read_text(encoding="utf-8").strip()
    if not content:
        return ""

    # Count attempts
    attempt_count = content.count("Attempt ")
    if attempt_count > 0:
        return f"Required {attempt_count} attempt(s) — see `lifecycle/{feature}/learnings/progress.txt`"
    return f"See `lifecycle/{feature}/learnings/progress.txt`"


def render_deferred_questions(data: ReportData) -> str:
    """Render the deferred questions section grouped by severity."""
    total = len(data.deferrals)
    lines: list[str] = [f"## Deferred Questions ({total})", ""]

    if not data.deferrals:
        lines.append("No questions were deferred — all ambiguities were resolved by the pipeline.")
        lines.append("")
        return "\n".join(lines)

    # Sort by severity (blocking first) then feature
    severity_order = {SEVERITY_BLOCKING: 0, SEVERITY_NON_BLOCKING: 1, SEVERITY_INFORMATIONAL: 2}
    sorted_deferrals = sorted(
        data.deferrals,
        key=lambda d: (severity_order.get(d.severity, 9), d.feature, d.question_id),
    )

    # Collect features that successfully merged to integration
    merged_to_integration: set[str] = set()
    for evt in data.events:
        if evt.get("event") == "feature_merged":
            feat = evt.get("feature", "")
            if feat:
                merged_to_integration.add(feat)

    for dq in sorted_deferrals:
        lines.append(f"### {dq.feature}: {dq.question} [{dq.severity}]")
        lines.append(f"> {dq.question}")
        lines.append(f"> Pipeline attempted: {dq.pipeline_attempted}")
        lines.append(f"> Full details: `deferred/{dq.feature}-q{dq.question_id:03d}.md`")

        if dq.severity == SEVERITY_BLOCKING:
            if dq.feature in merged_to_integration:
                action = (
                    "Feature is on the integration branch — do NOT re-run. "
                    "Investigate the post-merge failure (see error details above and overnight-events.log). "
                    "Address missed post-merge steps manually (review dispatch, backlog write-back)."
                )
            else:
                action = "Answer this question and re-run the feature"
        elif dq.severity == SEVERITY_NON_BLOCKING:
            action = "Validate the default choice made during implementation"
        else:
            action = "No action needed — review when convenient"
        lines.append(f"> **To unblock**: {action}")
        lines.append("")

    return "\n".join(lines)


def render_critical_review_residue(data: ReportData) -> str:
    """Render the critical review residue section from lifecycle residue files."""
    lifecycle_root = _resolve_user_project_root() / "cortex/lifecycle"
    residue_paths = sorted(lifecycle_root.glob("*/critical-review-residue.json"))
    total = len(residue_paths)
    lines: list[str] = [f"## Critical Review Residue ({total})", ""]

    if total == 0:
        lines.append(
            "No residue files this cycle. Absence may indicate: zero B-class findings, "
            "no lifecycle-context runs, or total reviewer failure (which does not write a residue file)."
        )
        lines.append("")
        return "\n".join(lines)

    for path in residue_paths:
        slug = path.parent.name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lines.append(f"Feature {slug}: residue file malformed, skipped.")
            lines.append("")
            continue

        feature = payload.get("feature", slug)
        findings = payload.get("findings", [])
        synthesis_status = payload.get("synthesis_status", "unknown")
        reviewers = payload.get("reviewers", {})
        completed = reviewers.get("completed", None)
        dispatched = reviewers.get("dispatched", None)

        lines.append(f"### {feature} ({len(findings)})")

        # Degraded annotations
        if synthesis_status != "ok":
            lines.append("> ⚠ degraded: synthesis failed")
        if (
            completed is not None
            and dispatched is not None
            and completed < dispatched
        ):
            lines.append(f"> ⚠ degraded: partial reviewer coverage ({completed} of {dispatched})")

        lines.append("")

        for finding in findings:
            reviewer_angle = finding.get("reviewer_angle", "unknown")
            finding_text = finding.get("finding", "")
            lines.append(f"- {reviewer_angle}: {finding_text}")

        lines.append("")

    return "\n".join(lines)


def render_failed_features(data: ReportData) -> str:
    """Render the failed/paused features section."""
    if data.state is None:
        return "## Failed Features (0)\n\nNo overnight state found.\n"

    failed = {
        name: fs for name, fs in data.state.features.items()
        if fs.status in ("failed", "paused")
    }
    total = len(failed)
    lines: list[str] = [f"## Failed Features ({total})", ""]

    if not failed:
        lines.append("All features completed or were deferred with questions.")
        lines.append("")
        return "\n".join(lines)

    # Collect circuit breaker info from batch results
    cb_features: set[str] = set()
    for br in data.batch_results:
        if br.get("circuit_breaker_fired", False):
            for fp in br.get("features_paused", []):
                if "circuit breaker" in (fp.get("error", "")).lower():
                    cb_features.add(fp["name"])

    # Count retry attempts from events
    retry_counts: dict[str, int] = {}
    for evt in data.events:
        if evt.get("event") == "retry_attempt":
            feat = evt.get("feature", "")
            retry_counts[feat] = retry_counts.get(feat, 0) + 1

    # Collect merge conflict details from events
    conflict_info: dict[str, dict] = {}
    for evt in data.events:
        if evt.get("event") == "merge_conflict_classified":
            feat = evt.get("feature", "")
            details = evt.get("details", {})
            if feat:
                conflict_info[feat] = details

    # Collect features that successfully merged to integration
    merged_to_integration: set[str] = set()
    for evt in data.events:
        if evt.get("event") == "feature_merged":
            feat = evt.get("feature", "")
            if feat:
                merged_to_integration.add(feat)

    for name, fs in sorted(failed.items()):
        error = fs.error or "unknown error"
        lines.append(f"### {name}: {error}")
        retries = retry_counts.get(name, 0)
        cb_status = "fired" if name in cb_features else "not triggered"
        lines.append(f"- Retry attempts: {retries}")
        lines.append(f"- Circuit breaker: {cb_status}")
        conflict = conflict_info.get(name)
        if conflict is not None:
            conflict_summary = conflict.get("conflict_summary", "")
            lines.append(f"- **Conflict summary**: {conflict_summary}")
            conflicted_files = conflict.get("conflicted_files", [])
            if conflicted_files:
                files_str = ", ".join(f"`{f}`" for f in conflicted_files)
                lines.append(f"- **Conflicted files**: {files_str}")
            lines.append(f"- **Recovery branch**: `pipeline/{name}`")
        lines.append(f"- Learnings: `lifecycle/{name}/learnings/progress.txt`")
        recovery_entry = _read_recovery_log_last_entry(name)
        if recovery_entry:
            lines.append(f"- **Last recovery attempt**: {recovery_entry}")

        # Cost
        if data.pipeline_events_path is not None:
            cost = _aggregate_feature_cost(name, data.pipeline_events_path)
            if cost is not None:
                lines.append(f"**Cost**: ${cost:.2f}")

        # Warn if the feature successfully merged to integration
        if name in merged_to_integration:
            lines.append(
                "- \u26a0\ufe0f Feature is on the integration branch \u2014 "
                "merge succeeded but a post-merge step failed after the commit landed."
            )

        # Suggested next step
        if name in merged_to_integration:
            suggestion = (
                "Investigate which post-merge step crashed (check overnight-events.log "
                "for the feature_deferred event details and error field). Do NOT re-run "
                "the feature \u2014 it is already on the integration branch. Address any "
                "missed post-merge steps manually (e.g., trigger review, update backlog item)."
            )
        else:
            suggestion = _suggest_next_step(error)
        lines.append(f"- **Suggested next step**: {suggestion}")

        # Last worker output snippet
        if data.pipeline_events_path is not None:
            snippet = _read_last_task_output(name, data.pipeline_events_path)
        else:
            snippet = ""
        if snippet:
            lines.append(f"- **Last worker output**: {snippet}")
        lines.append("")

    return "\n".join(lines)


def collect_tool_failures(session_id: str) -> dict[str, dict[str, Any]]:
    """Collect tool failure data from the session-scoped failure directory.

    Prefers ``lifecycle/sessions/{session_id}/tool-failures/`` (the post-#163
    location written by the PostToolUse hook when ``$LIFECYCLE_SESSION_ID`` is
    set) and falls back to ``${TMPDIR:-/tmp}/claude-tool-failures-{session_id}/``
    only when the lifecycle path is absent (interactive sessions and pre-#163
    overnight runs). Reads per-tool ``.count`` and ``.log`` files.

    Args:
        session_id: The session identifier used by the hook (may also be a
            date-based fallback key such as ``date-YYYYMMDD``).

    Returns:
        Mapping of tool_key -> ``{"count": int, "last_exit_code": str}`` for
        each tool that has recorded at least one failure.  Returns an empty
        dict when neither directory is present or contains no failure records.
    """
    lifecycle_dir = Path(f"lifecycle/sessions/{session_id}/tool-failures")
    if lifecycle_dir.is_dir():
        track_dir = lifecycle_dir
    else:
        tmpdir = os.environ.get("TMPDIR", "/tmp")
        track_dir = Path(f"{tmpdir}/claude-tool-failures-{session_id}")
    if not track_dir.is_dir():
        return {}

    result: dict[str, dict[str, Any]] = {}

    try:
        count_files = list(track_dir.glob("*.count"))
    except OSError:
        return {}

    for count_file in count_files:
        tool_key = count_file.stem  # e.g. "bash"
        try:
            count_text = count_file.read_text(encoding="utf-8").strip()
            count = int(count_text) if count_text.isdigit() else 0
        except (OSError, ValueError):
            count = 0

        if count == 0:
            continue

        last_exit_code = _read_last_exit_code(track_dir / f"{tool_key}.log")
        result[tool_key] = {"count": count, "last_exit_code": last_exit_code}

    return result


def _read_last_exit_code(log_file: Path) -> str:
    """Extract the exit_code from the last failure entry in a tool log file.

    The hook appends YAML-like blocks separated by ``---`` lines.  This
    function splits on those separators and looks for an ``exit_code:`` line
    in the final non-empty block.

    Args:
        log_file: Path to the ``.log`` file written by the hook.

    Returns:
        The exit code string from the last entry, or ``"unknown"`` on any
        error or if the file is absent/malformed.
    """
    try:
        text = log_file.read_text(encoding="utf-8")
    except OSError:
        return "unknown"

    # Split on '---' separators; take the last non-empty block.
    blocks = [b.strip() for b in text.split("---") if b.strip()]
    if not blocks:
        return "unknown"

    for line in blocks[-1].splitlines():
        stripped = line.strip()
        if stripped.startswith("exit_code:"):
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()

    return "unknown"


# ---------------------------------------------------------------------------
# Sandbox-denial classifier (spec R3)
# ---------------------------------------------------------------------------

# Plumbing-tool prefix words used by Layer 2/3 of the classifier.  Per spec R3,
# this is a closed enumeration; tools NOT in this set with EPERM stderr fall
# through to ``unclassified_eperm`` (likely non-sandbox: chmod / ACL / EROFS).
PLUMBING_TOOLS = {"git", "gh", "npm", "pnpm", "yarn", "cargo", "hg", "jj"}


# Known-plumbing-write-target subcommand → repo-relative target suffixes.
# Each entry maps a tuple of leading words (after optional ``cd`` prefix
# stripping) to a list of target-suffix templates resolved against the
# inferred repo dir.  ``{HEAD}`` is a placeholder for the current branch
# name (we do not parse that from disk; we substitute ``*`` so the union
# match treats any ``refs/heads/<name>`` entry as a candidate).  Templates
# starting with ``refs/remotes/`` similarly use ``*`` for unknown remote/
# branch fields when the command does not provide them.
#
# Per spec R3 enumeration:
#   git commit (and --amend, merge, rebase, reset) → refs/heads/<HEAD>,
#       HEAD, packed-refs, index
#   git push <remote> <branch>                       → refs/remotes/<remote>/<branch>,
#                                                      packed-refs
#   git tag <name>                                   → refs/tags/<name>
#   git fetch                                        → refs/remotes/..., FETCH_HEAD
_GIT_COMMIT_TARGETS = (
    ".git/refs/heads/*",
    ".git/HEAD",
    ".git/packed-refs",
    ".git/index",
)


def collect_sandbox_denials(session_id: str) -> dict[str, int]:
    """Classify per-session Bash sandbox denials into closed-enum categories.

    Reads ``lifecycle/sessions/<session_id>/tool-failures/bash.log`` (the
    tracker's per-session bash failure log, with ``command:`` and ``stderr:``
    fields per spec R3a) and the union of ``lifecycle/sessions/<session_id>/
    sandbox-deny-lists/*.json`` sidecar deny-lists (per spec R2).  Filters to
    failures whose stderr contains ``Operation not permitted`` and runs the
    four-layer classifier:

    - L1 (shell redirection): ``>file``, ``>>file``, ``tee file``,
      ``echo … > file``, ``cat … > file`` candidate targets.
    - L2 (plumbing-tool subcommand mapping): leading word in
      :data:`PLUMBING_TOOLS` and subcommand in the known mapping → generate
      candidate targets relative to the ``cd`` arg or known repo paths.
    - L3 (plumbing fallthrough): leading word in :data:`PLUMBING_TOOLS` but
      no specific subcommand match → ``plumbing_eperm``.
    - L4 (other fallthrough): no plumbing leader → ``unclassified_eperm``.

    L1/L2 candidate targets are looked up against the union of sidecar
    ``deny_paths`` and classified by path-pattern (home_repo_*, cross_repo_*,
    or other_deny_path).  Home/cross repo roots are inferred at classification
    time from ``lifecycle/overnight-state.json``: home is ``state.project_root``
    and cross is the set of distinct non-home ``feature.repo_path`` values.

    The entire body is wrapped in a top-level exception envelope that returns
    ``{}`` on any error (mirrors the existing ``collect_tool_failures``
    precedent), so a single malformed sidecar or bash.log does not crash the
    morning report.

    Args:
        session_id: The overnight session identifier
            (``overnight-YYYY-MM-DD-HHMM``).

    Returns:
        Dict mapping category → count.  Categories (closed list per spec):
        ``home_repo_refs``, ``cross_repo_refs``, ``home_repo_head``,
        ``home_repo_packed_refs``, ``cross_repo_head``,
        ``cross_repo_packed_refs``, ``other_deny_path``, ``plumbing_eperm``,
        ``unclassified_eperm``.  Returns ``{}`` if the session directory is
        absent, the bash log is missing, or any unhandled error occurs.
    """
    try:
        import yaml  # local import; yaml is already an indirect dep

        session_root = Path(f"lifecycle/sessions/{session_id}")
        bash_log = session_root / "tool-failures" / "bash.log"
        sidecar_dir = session_root / "sandbox-deny-lists"

        if not bash_log.is_file():
            return {}

        # --- Build the union of sidecar deny_paths (per-spawn JSONs). ----
        deny_union: set[str] = set()
        if sidecar_dir.is_dir():
            for sidecar in sorted(sidecar_dir.glob("*.json")):
                try:
                    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    print(
                        f"collect_sandbox_denials: skipping malformed sidecar "
                        f"{sidecar}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                deny_paths = (
                    sidecar_data.get("deny_paths")
                    if isinstance(sidecar_data, dict)
                    else None
                )
                # Reader-side mirror of T4/T5 writer-side guard.
                if not (
                    isinstance(deny_paths, list)
                    and all(isinstance(p, str) for p in deny_paths)
                ):
                    print(
                        f"collect_sandbox_denials: skipping sidecar {sidecar} "
                        f"with invalid deny_paths shape",
                        file=sys.stderr,
                    )
                    continue
                deny_union.update(deny_paths)

        # --- Resolve home/cross repo roots from overnight-state.json. ----
        home_repo_root: Optional[str] = None
        cross_repo_roots: list[str] = []
        try:
            state = load_state()
            home_repo_root = state.project_root
            cross_repo_roots = sorted({
                feat.repo_path
                for feat in state.features.values()
                if feat.repo_path is not None
                and feat.repo_path != state.project_root
            })
        except Exception as exc:
            print(
                f"collect_sandbox_denials: unable to load overnight state "
                f"for {session_id}: {exc}; home/cross classification will "
                f"collapse to other_deny_path",
                file=sys.stderr,
            )

        # --- Iterate failure entries and classify. -----------------------
        counts: dict[str, int] = {}
        text = bash_log.read_text(encoding="utf-8")
        for doc in yaml.safe_load_all(text):
            # Per-entry shape guard (spec): skip non-dict YAML docs.
            if not isinstance(doc, dict):
                continue
            stderr_blob = doc.get("stderr") or ""
            if not isinstance(stderr_blob, str):
                continue
            if "Operation not permitted" not in stderr_blob:
                continue
            command = doc.get("command") or ""
            if not isinstance(command, str):
                continue

            category = _classify_sandbox_denial(
                command=command,
                deny_union=deny_union,
                home_repo_root=home_repo_root,
                cross_repo_roots=cross_repo_roots,
            )
            counts[category] = counts.get(category, 0) + 1

        return counts
    except Exception as exc:  # noqa: BLE001 - documented top-level envelope
        print(
            f"collect_sandbox_denials: unhandled error for session "
            f"{session_id}: {exc}; returning empty dict",
            file=sys.stderr,
        )
        return {}


def _strip_cd_prefix(command: str) -> tuple[Optional[str], str]:
    """Strip an optional ``cd <dir> && …`` prefix.

    Returns ``(cd_dir, remainder)`` where ``cd_dir`` is the argument to
    ``cd`` (or ``None`` if no prefix was present) and ``remainder`` is the
    command following ``&&``.  When no ``cd`` prefix is present, returns
    ``(None, command)``.
    """
    # Match: cd <dir> && rest  (allow leading whitespace and quoted dir)
    m = re.match(r"\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*&&\s*(.+)", command, re.DOTALL)
    if not m:
        return None, command
    cd_dir = m.group(1).strip().strip("\"'")
    return cd_dir, m.group(2)


def _extract_redirect_targets(command: str) -> list[str]:
    """Extract candidate redirect targets from a command (Layer 1).

    Recognizes ``>file``, ``>>file``, ``tee file``, ``tee -a file`` forms
    and returns a list of target tokens (paths as written, before any
    repo-dir resolution).  Uses a focused tokenizer rather than a full Bash
    parser (per spec).
    """
    targets: list[str] = []
    # > file or >> file (allow optional whitespace, capture next token)
    for m in re.finditer(r">>?\s*(\"[^\"]+\"|'[^']+'|[^\s|;&<>]+)", command):
        token = m.group(1).strip().strip("\"'")
        # Skip stderr-redirect tokens like &1 / &2.
        if token.startswith("&"):
            continue
        targets.append(token)
    # tee [-a] file
    for m in re.finditer(r"\btee\s+(?:-a\s+)?(\"[^\"]+\"|'[^']+'|\S+)", command):
        token = m.group(1).strip().strip("\"'")
        targets.append(token)
    return targets


def _resolve_target(repo_dir: Optional[str], target: str) -> str:
    """Resolve a candidate target relative to a repo dir, if not absolute."""
    if os.path.isabs(target):
        return target
    if repo_dir:
        return os.path.normpath(os.path.join(repo_dir, target))
    return target


def _layer2_git_targets(repo_dir: Optional[str], remainder: str) -> Optional[list[str]]:
    """Return Layer-2 candidate targets for known ``git`` subcommands.

    Returns ``None`` if the subcommand is not in the known mapping (caller
    should fall through to Layer 3 ``plumbing_eperm``).
    """
    tokens = remainder.strip().split()
    if not tokens or tokens[0] != "git":
        return None
    if len(tokens) < 2:
        return None
    sub = tokens[1]
    targets: list[str] = []
    if sub in {"commit", "merge", "rebase", "reset"}:
        targets = list(_GIT_COMMIT_TARGETS)
    elif sub == "push":
        # git push <remote> <branch>
        remote = tokens[2] if len(tokens) >= 3 else "*"
        branch = tokens[3] if len(tokens) >= 4 else "*"
        # Skip flag-style positional args.
        if remote.startswith("-"):
            remote = "*"
        if branch.startswith("-"):
            branch = "*"
        targets = [
            f".git/refs/remotes/{remote}/{branch}",
            ".git/packed-refs",
        ]
    elif sub == "tag":
        name = tokens[2] if len(tokens) >= 3 else "*"
        if name.startswith("-"):
            name = "*"
        targets = [f".git/refs/tags/{name}"]
    elif sub == "fetch":
        targets = [
            ".git/refs/remotes/*",
            ".git/FETCH_HEAD",
        ]
    else:
        return None
    return [_resolve_target(repo_dir, t) for t in targets]


def _path_pattern_classify(
    path: str,
    home_repo_root: Optional[str],
    cross_repo_roots: list[str],
) -> str:
    """Classify a deny-list-matched path into a closed-enum category."""

    def _match(root: str, path: str, kind: str) -> Optional[str]:
        # Normalize both for fair comparison.
        root_n = os.path.normpath(root)
        # ``.git/HEAD`` exact (one path) vs ``.git/refs/heads/*`` (any ref).
        head = os.path.join(root_n, ".git", "HEAD")
        packed = os.path.join(root_n, ".git", "packed-refs")
        refs_prefix = os.path.join(root_n, ".git", "refs", "heads") + os.sep
        if path == head:
            return f"{kind}_head"
        if path == packed:
            return f"{kind}_packed_refs"
        if path.startswith(refs_prefix):
            return f"{kind}_refs"
        return None

    if home_repo_root:
        cat = _match(home_repo_root, path, "home_repo")
        if cat is not None:
            return cat
    for cross in cross_repo_roots:
        cat = _match(cross, path, "cross_repo")
        if cat is not None:
            return cat
    return "other_deny_path"


def _glob_match_in_union(candidate: str, deny_union: set[str]) -> Optional[str]:
    """Match a candidate target against the deny-list union.

    Supports ``*`` wildcards in the candidate (Layer 2 emits ``*`` for
    unknown ref/remote/branch fields).  Returns the matched deny-list path,
    or ``None`` if no entry matches.
    """
    if "*" not in candidate:
        if candidate in deny_union:
            return candidate
        return None
    # Translate the candidate to a regex (only ``*`` needs escaping).
    parts = candidate.split("*")
    pattern = ".*".join(re.escape(p) for p in parts)
    rx = re.compile("^" + pattern + "$")
    for entry in deny_union:
        if rx.match(entry):
            return entry
    return None


def _classify_sandbox_denial(
    command: str,
    deny_union: set[str],
    home_repo_root: Optional[str],
    cross_repo_roots: list[str],
) -> str:
    """Run the four-layer classifier on a single denied command."""
    cd_dir, remainder = _strip_cd_prefix(command)
    repo_dir = cd_dir  # may be None

    # Layer 1 — shell redirection.
    redirect_targets = _extract_redirect_targets(remainder)
    if redirect_targets:
        for tgt in redirect_targets:
            resolved = _resolve_target(repo_dir, tgt)
            matched = _glob_match_in_union(resolved, deny_union)
            if matched is not None:
                return _path_pattern_classify(
                    matched, home_repo_root, cross_repo_roots
                )
        # L1 produced candidates but none matched the deny-list — fall
        # through to L3/L4 below per spec ("If Layer 1 or Layer 2 produced
        # a candidate target but the deny-list lookup did NOT match, fall
        # through to the Layer 3/4 buckets above.").

    # Determine leading command word (after optional cd prefix).
    leading_match = re.match(r"\s*(\S+)", remainder)
    leading = leading_match.group(1) if leading_match else ""

    # Layer 2 — plumbing-tool subcommand mapping (currently ``git`` only).
    if leading in PLUMBING_TOOLS:
        l2_targets = _layer2_git_targets(repo_dir, remainder)
        if l2_targets is not None:
            for tgt in l2_targets:
                matched = _glob_match_in_union(tgt, deny_union)
                if matched is not None:
                    return _path_pattern_classify(
                        matched, home_repo_root, cross_repo_roots
                    )
            # L2 produced candidates but none matched — fall through to L3.
        # Layer 3 — plumbing fallback.
        return "plumbing_eperm"

    # Layer 4 — other fallthrough.
    return "unclassified_eperm"


def render_scheduled_fire_failures(data: ReportData) -> str:
    """Render the scheduled-fire failures section (spec §R13).

    When the launchd-fired launcher script (Task 3) cannot spawn the
    cortex binary at fire time (TCC EPERM, missing binary, etc.), it
    writes a sentinel ``<session_dir>/scheduled-fire-failed.json``. This
    section surfaces every such marker found by
    :func:`fail_markers.scan_session_dirs`, with timestamp, error class,
    session id, and the absolute path to the marker JSON for diagnostics.

    Returns the empty string when the list is empty so the section is
    omitted entirely from the report.
    """
    failures = data.scheduled_fire_failures
    if not failures:
        return ""

    total = len(failures)
    plural = "s" if total != 1 else ""
    lines: list[str] = [f"## Scheduled-Fire Failures ({total})", ""]
    lines.append(
        "The launchd-fired launcher could not spawn the cortex runner at fire "
        f"time for {total} scheduled overnight{plural}. Inspect each marker "
        "for the error class and text, then grant Full Disk Access to the "
        "cortex binary or fix the binary path before the next schedule."
    )
    lines.append("")

    for failure in failures:
        marker_path = Path(failure.session_dir) / "scheduled-fire-failed.json"
        lines.append(f"### {failure.session_id} — {failure.error_class}")
        lines.append(f"- Time: {failure.ts}")
        lines.append(f"- Error class: {failure.error_class}")
        lines.append(f"- Error text: {failure.error_text}")
        lines.append(f"- launchd label: `{failure.label}`")
        lines.append(f"- Marker: `{marker_path}`")
        lines.append("")

    return "\n".join(lines)


def render_new_backlog_items(data: ReportData) -> str:
    """Render the new backlog items section."""
    lines: list[str] = ["## New Backlog Items", ""]

    if not data.new_backlog_items:
        lines.append("No new backlog items created.")
        lines.append("")
        return "\n".join(lines)

    for item in data.new_backlog_items:
        lines.append(f"- **#{item.id:03d}** [{item.type}] {item.title} — {item.reason}")

    lines.append("")
    return "\n".join(lines)


def _suggest_next_step(error: str) -> str:
    """Derive a suggested next step from an error message."""
    error_lower = error.lower()
    if "merge conflict" in error_lower or "conflict" in error_lower:
        return "Resolve conflict manually, then retry"
    if "test fail" in error_lower:
        return "Investigate test failure, fix, retry"
    if "circuit breaker" in error_lower:
        return "Review learnings, consider spec revision"
    if "already implemented" in error_lower or "already merged" in error_lower:
        return "Verify prior merge on main, close backlog item if complete"
    if "no changes produced" in error_lower:
        return "Check agent output — agent ran but produced no diff"
    return "Review learnings, retry or investigate"


def _read_last_task_output(
    feature: str,
    pipeline_events_path: Path = Path("lifecycle/pipeline-events.log"),
) -> str:
    """Read the most recent task_output event for a feature from the pipeline events log.

    Args:
        feature: The feature name to search for.
        pipeline_events_path: Path to the pipeline events log file.

    Returns:
        The output field of the last matching event truncated to 500 chars,
        or an empty string if the file is missing, unreadable, or no matching
        event exists.
    """
    try:
        lines = pipeline_events_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    last_match: dict | None = None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "task_output" and event.get("feature") == feature:
            last_match = event

    if last_match is None:
        return ""

    output = last_match.get("output", "")
    return output[:500]


def _aggregate_feature_cost(
    feature_name: str,
    pipeline_events_path: Path,
) -> Optional[float]:
    """Sum cost_usd from all dispatch_complete events for a feature.

    Args:
        feature_name: The feature to aggregate costs for.
        pipeline_events_path: Path to pipeline-events.log (JSONL).

    Returns:
        Total cost in USD, or None if the file is absent or no matching
        events exist.
    """
    try:
        lines = pipeline_events_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    total: float = 0.0
    found = False
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            event.get("event") == "dispatch_complete"
            and event.get("feature") == feature_name
        ):
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                total += cost
                found = True

    return total if found else None


def render_action_checklist(data: ReportData) -> str:
    """Render the contextual what-to-do-next checklist."""
    lines: list[str] = ["## What to Do Next", ""]
    item_num = 1

    # Deferred questions
    if data.deferrals:
        n = len(data.deferrals)
        lines.append(f"{item_num}. [ ] Answer {n} deferred question{'s' if n != 1 else ''} in `deferred/`")
        item_num += 1

    # Completed features
    if data.state:
        merged = [n for n, fs in data.state.features.items() if fs.status == "merged"]
        if merged:
            lines.append(f"{item_num}. [ ] Try completed features: {', '.join(merged)}")
            item_num += 1

    # Failed features
    if data.state:
        failed = sum(1 for fs in data.state.features.values() if fs.status in ("failed", "paused"))
        if failed:
            lines.append(f"{item_num}. [ ] Investigate {failed} failed feature{'s' if failed != 1 else ''}")
            item_num += 1

    # Integration tests
    lines.append(f"{item_num}. [ ] Run integration tests")
    lines.append("")

    return "\n".join(lines)


def render_run_statistics(data: ReportData) -> str:
    """Render detailed run statistics."""
    lines: list[str] = ["## Run Statistics", ""]

    # Rounds — use state (authoritative) consistent with executive summary
    round_completes = [e for e in data.events if e.get("event") == "round_complete"]
    rounds_from_state = len(data.state.round_history) if data.state else 0
    rounds_display = rounds_from_state if rounds_from_state > 0 else len(round_completes)
    lines.append(f"- Rounds completed: {rounds_display}")

    # Per-round timing
    round_starts = {e.get("round"): e.get("ts") for e in data.events if e.get("event") == "round_start"}
    round_ends = {e.get("round"): e.get("ts") for e in data.events if e.get("event") == "round_complete"}

    timing_parts: list[str] = []
    for rnd in sorted(set(round_starts) | set(round_ends)):
        if rnd is None:
            continue
        start_ts = round_starts.get(rnd)
        end_ts = round_ends.get(rnd)
        if start_ts and end_ts:
            try:
                delta = datetime.fromisoformat(end_ts) - datetime.fromisoformat(start_ts)
                mins = int(delta.total_seconds() / 60)
                timing_parts.append(f"Round {rnd}: {mins}m")
            except (ValueError, TypeError):
                timing_parts.append(f"Round {rnd}: unknown")
        else:
            timing_parts.append(f"Round {rnd}: incomplete")

    if timing_parts:
        lines.append(f"- Per-round timing: {', '.join(timing_parts)}")

    # Circuit breaker activations
    cb_count = sum(1 for e in data.events if e.get("event") == "circuit_breaker")
    lines.append(f"- Circuit breaker activations: {cb_count}")

    # Total features
    if data.state:
        lines.append(f"- Total features processed: {len(data.state.features)}")

    # Total session cost
    if data.pipeline_events_path is not None and data.state:
        feature_costs = [
            _aggregate_feature_cost(name, data.pipeline_events_path)
            for name in data.state.features
        ]
        known_costs = [c for c in feature_costs if c is not None]
        if known_costs:
            session_total = sum(known_costs)
            lines.append(f"- Total session cost: ${session_total:.2f}")

    lines.append("")

    return "\n".join(lines)


def render_tool_failures(data: ReportData) -> str:
    """Render the tool failures section.

    Lists per-tool failure counts and last exit codes recorded by the
    PostToolUse hook during this session.  The section is omitted entirely
    (returns an empty string) when no failures were recorded, keeping the
    report clean for clean runs.

    Args:
        data: Aggregated report data containing ``tool_failures``.

    Returns:
        Markdown-formatted section string, or ``""`` when no failures exist.
    """
    if not data.tool_failures:
        return ""

    lines: list[str] = ["## Tool Failures", ""]
    for tool_name in sorted(data.tool_failures):
        info = data.tool_failures[tool_name]
        count = info.get("count", 0)
        last_exit = info.get("last_exit_code", "unknown")
        lines.append(f"- **{tool_name}**: {count} failure{'s' if count != 1 else ''}, last exit code: `{last_exit}`")
    lines.append("")
    return "\n".join(lines)


# Spec R4: ordered list of (category-key, human-readable-label) pairs.  The
# key matches the closed-enum returned by ``collect_sandbox_denials``; the
# label is the verbatim bullet prefix from the spec.  Order is load-bearing
# (home → cross → other → plumbing → unclassified).
_SANDBOX_DENIAL_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("home_repo_refs", "Home-repo refs"),
    ("home_repo_head", "Home-repo HEAD"),
    ("home_repo_packed_refs", "Home-repo packed-refs"),
    ("cross_repo_refs", "Cross-repo refs"),
    ("cross_repo_head", "Cross-repo HEAD"),
    ("cross_repo_packed_refs", "Cross-repo packed-refs"),
    ("other_deny_path", "Other deny-list paths"),
    ("plumbing_eperm", "Plumbing EPERM (likely sandbox, unmapped subcommand)"),
    (
        "unclassified_eperm",
        "Unclassified EPERM (likely non-sandbox: chmod / ACL / EROFS / gpg)",
    ),
)

# Spec R4: verbatim disclosure paragraph required by Adversarial #A9 plus the
# within-Bash plumbing caveat raised by critical review.  Acceptance gates
# `grep -F 'Bash-routed sandbox denials'` and `grep -F 'V1 scope'` against
# this exact text.
_SANDBOX_DENIAL_DISCLOSURE = (
    "Bash-routed sandbox denials caught by per-spawn `denyWrite` enforcement "
    "(#163). Within Bash scope, `git`/`gh`/`npm`-class plumbing denials are "
    "classified by command-target inference (precise) when the subcommand is "
    "in the known mapping and falls through to the `plumbing_eperm` bucket "
    "otherwise. Write/Edit/MCP escape paths are NOT covered — see #163 V1 "
    "scope."
)


def render_sandbox_denials(data: ReportData) -> str:
    """Render the sandbox-denials section per spec R4.

    Returns the empty string when ``data.sandbox_denials`` is empty (the
    section is omitted from the morning report).  Otherwise emits a
    ``## Sandbox Denials (<total>)`` section containing the verbatim
    disclosure paragraph followed by a bullet list with one line per
    category whose count is ≥ 1 (zero-count categories are suppressed).

    Args:
        data: Aggregated report data containing ``sandbox_denials``.

    Returns:
        Markdown-formatted section string, or ``""`` when no denials exist.
    """
    if not data.sandbox_denials:
        return ""

    total = sum(data.sandbox_denials.values())
    lines: list[str] = [
        f"## Sandbox Denials ({total})",
        "",
        _SANDBOX_DENIAL_DISCLOSURE,
        "",
    ]
    for key, label in _SANDBOX_DENIAL_CATEGORIES:
        count = data.sandbox_denials.get(key, 0)
        if count >= 1:
            lines.append(f"- {label}: {count}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level report generation
# ---------------------------------------------------------------------------

def generate_report(data: ReportData) -> str:
    """Assemble the complete morning report from all sections."""
    sections: list[str] = [
        f"# Morning Report: {data.date}",
        "",
    ]
    # Spec Req 20: unconditional header when CORTEX_SANDBOX_SOFT_FAIL=1 was
    # active at any settings-builder invocation during the session. The event
    # `sandbox_soft_fail_active` is emitted by the per-spawn settings builder
    # (cortex_command.overnight.sandbox_settings) at first activation.
    soft_fail_header = render_soft_fail_header(data)
    if soft_fail_header:
        sections.append(soft_fail_header)
        sections.append("")
    sections.extend([
        render_executive_summary(data),
        render_completed_features(data),
        render_pending_drift(data),
        render_deferred_questions(data),
        render_critical_review_residue(data),
        render_failed_features(data),
        render_new_backlog_items(data),
        render_action_checklist(data),
        render_run_statistics(data),
    ])
    # Scheduled-fire failures section is omitted entirely when empty.
    fire_failures_section = render_scheduled_fire_failures(data)
    if fire_failures_section:
        sections.append(fire_failures_section)
    # Tool failures section is omitted entirely when there are no failures
    tool_failures_section = render_tool_failures(data)
    if tool_failures_section:
        sections.append(tool_failures_section)
    # Sandbox denials section (spec R4/R5) — omitted entirely when no
    # classified denials were collected for this session.
    sandbox_denials_section = render_sandbox_denials(data)
    if sandbox_denials_section:
        sections.append(sandbox_denials_section)
    return "\n".join(sections)


def write_report(
    report: str,
    path: Optional[Path] = None,
) -> Path:
    """Atomically write the morning report to disk.

    Uses temp file + os.replace for safe writes.

    Args:
        report: Rendered report text.
        path: Destination path. Defaults to ``_default_report_path()``
            resolved at call time.
    """
    path = path if path is not None else _default_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".morning-report-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, report.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, path)
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return path


def notify(message: str) -> None:
    """Send a notification via the Claude notification hook."""
    hook = Path.home() / ".claude" / "notify.sh"
    try:
        subprocess.run([str(hook), message], check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def generate_and_write_report(
    state_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
    pr_urls: Optional[dict[str, str]] = None,
    report_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Path:
    """Convenience entry point: collect data, generate, write, and notify.

    Called by the bash runner post-loop:
        python3 -c "from cortex_command.overnight.report import generate_and_write_report; generate_and_write_report()"

    Args:
        state_path: Path to overnight-state.json. Defaults to
            ``_default_state_path()`` resolved at call time.
        events_path: Path to overnight-events.log. Defaults to
            ``_default_log_path()`` resolved at call time.
        pr_urls: Optional mapping of os.path.realpath(repo_path) -> PR URL.
            Written to data.pr_urls before rendering. When provided, PR URLs
            appear in the completed features section and notification.
        report_dir: Optional directory to write the session-specific report
            into. When provided, the report is written to
            ``report_dir / "morning-report.md"`` without checking whether
            the directory already exists (write_report creates parents).
            When None, the report path is derived from the session dir.
        results_dir: Optional directory containing batch-*-results.json
            files.  Passed through to collect_report_data.
        project_root: Optional target project root.  When provided, the
            latest-copy morning report is written to
            ``project_root / "cortex/lifecycle" / "morning-report.md"`` instead
            of ``_default_report_path()`` (the user's project root resolved
            at call time).
    """
    state_path = state_path or _default_state_path()
    events_path = events_path or _default_log_path()
    user_root = _resolve_user_project_root()
    lifecycle_root = user_root / "cortex/lifecycle"
    data = collect_report_data(
        state_path=state_path,
        events_path=events_path,
        deferred_dir=deferred_dir,
        results_dir=results_dir,
    )
    data.pr_urls = pr_urls or {}
    if data.state and data.state.worktree_path:
        followup_backlog_dir = Path(data.state.worktree_path) / "backlog"
    else:
        followup_backlog_dir = user_root / "backlog"
    data.new_backlog_items = create_followup_backlog_items(
        data, backlog_dir=followup_backlog_dir
    )
    report = generate_report(data)

    # Determine report output path
    report_path: Optional[Path] = None
    if report_dir is not None:
        report_path = report_dir / "morning-report.md"
    elif data.state and data.state.session_id:
        sdir = session_dir(data.state.session_id, lifecycle_root=lifecycle_root)
        if sdir.is_dir():
            report_path = sdir / "morning-report.md"
        else:
            print(
                f"warning: session dir {sdir} does not exist; "
                f"skipping report write",
                file=sys.stderr,
            )
    else:
        print(
            "warning: no session_id in state; skipping report write",
            file=sys.stderr,
        )

    if report_path is not None:
        path = write_report(report, path=report_path)

        # Keep a latest-copy at the well-known lifecycle location
        latest_copy_path = (
            project_root / "cortex/lifecycle" / "morning-report.md"
            if project_root is not None
            else lifecycle_root / "morning-report.md"
        )
        write_report(report, path=latest_copy_path)

        if data.pr_urls:
            pr_lines = "\n".join(data.pr_urls.values())
            notify(f"Overnight run complete — see {path}\n{pr_lines}")
        else:
            notify(f"Overnight run complete — see {path}")
        return path

    # No valid session dir — still notify but do not write
    if data.pr_urls:
        pr_lines = "\n".join(data.pr_urls.values())
        notify(f"Overnight run complete — report not written (no session dir)\n{pr_lines}")
    else:
        notify("Overnight run complete — report not written (no session dir)")
    return _default_report_path()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate overnight morning report")
    parser.add_argument(
        "--interrupted",
        action="store_true",
        default=False,
        help="Prepend an Interrupted Session header (for kill/crash emergency reports)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Session ID to generate report for (e.g. overnight-2026-03-06-1913)",
    )
    args = parser.parse_args()

    _cli_user_root = _resolve_user_project_root()
    _cli_lifecycle_root = _cli_user_root / "cortex/lifecycle"

    if args.session:
        sdir = session_dir(args.session, lifecycle_root=_cli_lifecycle_root)
        state_path = sdir / "overnight-state.json"
        events_path = sdir / "overnight-events.log"
        pipeline_events_path = sdir / "pipeline-events.log"
        data = collect_report_data(
            state_path=state_path,
            events_path=events_path,
            pipeline_events_path=pipeline_events_path,
        )
    else:
        data = collect_report_data()
    if data.state and data.state.worktree_path:
        followup_backlog_dir = Path(data.state.worktree_path) / "backlog"
    else:
        followup_backlog_dir = _cli_user_root / "backlog"
    data.new_backlog_items = create_followup_backlog_items(
        data, backlog_dir=followup_backlog_dir
    )
    report = generate_report(data)

    if args.interrupted:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"> **Interrupted Session** — partial report generated at {ts}\n\n"
        report = header + report

    # Determine report output path from session dir
    report_path = None
    if data.state and data.state.session_id:
        sdir = session_dir(data.state.session_id, lifecycle_root=_cli_lifecycle_root)
        if sdir.is_dir():
            report_path = sdir / "morning-report.md"
        else:
            print(
                f"warning: session dir {sdir} does not exist; "
                f"skipping report write",
                file=sys.stderr,
            )
    else:
        print(
            "warning: no session_id in state; skipping report write",
            file=sys.stderr,
        )

    if report_path is not None:
        path = write_report(report, path=report_path)
        print(f"Report written to {path}", file=sys.stderr)
    else:
        print("Report not written (no session dir)", file=sys.stderr)
