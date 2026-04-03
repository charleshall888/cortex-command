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

from claude.common import atomic_write, slugify

from claude.overnight.deferral import (
    DEFAULT_DEFERRED_DIR,
    SEVERITY_BLOCKING,
    SEVERITY_INFORMATIONAL,
    SEVERITY_NON_BLOCKING,
    DeferralQuestion,
    read_deferrals,
)
from claude.overnight.events import DEFAULT_LOG_PATH, read_events
from claude.overnight.state import DEFAULT_STATE_PATH, OvernightState, _LIFECYCLE_ROOT, load_state, session_dir


# ---------------------------------------------------------------------------
# Report data collection
# ---------------------------------------------------------------------------

DEFAULT_REPORT_PATH = _LIFECYCLE_ROOT / "morning-report.md"


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


def collect_report_data(
    state_path: Path = DEFAULT_STATE_PATH,
    events_path: Path = DEFAULT_LOG_PATH,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
    results_dir: Optional[Path] = None,
    pipeline_events_path: Optional[Path] = None,
) -> ReportData:
    """Collect all data sources needed for the morning report.

    Args:
        state_path: Path to overnight-state.json.
        events_path: Path to overnight-events.log.
        deferred_dir: Directory containing deferral markdown files.
        results_dir: Directory containing batch-*-results.json files.
            When None, resolved from session_id via session_dir().
        pipeline_events_path: Path to pipeline-events.log for worker
            output extraction.  When None, resolved from session_id
            via session_dir().

    Returns:
        ReportData with all fields populated from available sources.
    """
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
            sdir = session_dir(data.session_id, lifecycle_root=_LIFECYCLE_ROOT)
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
            sdir = session_dir(data.session_id, lifecycle_root=_LIFECYCLE_ROOT)
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
    else:
        # Fall back to today's date-based key (mirrors the hook's fallback)
        date_key = f"date-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        data.tool_failures = collect_tool_failures(date_key)

    return data


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def collect_tool_failures(session_id: str) -> dict[str, dict]:
    """Read tool failure data from the session-scoped /tmp failure directory.

    Reads ``/tmp/claude-tool-failures-{session_id}/`` and parses per-tool
    failure counts and last exit codes written by the PostToolUse hook
    (``cortex-tool-failure-tracker.sh``).

    Each tool produces two files:
    - ``{tool_key}.count`` — current failure count (integer, one line).
    - ``{tool_key}.log``   — YAML-like entries separated by ``---`` lines,
      each entry containing ``tool:``, ``exit_code:``, ``timestamp:``, and
      optional ``stderr:`` fields.

    Args:
        session_id: The session identifier used to locate the failure dir.

    Returns:
        Dict mapping original tool name to ``{"count": int, "last_exit_code": str}``.
        Returns an empty dict when the directory is absent, unreadable, or
        no failures were recorded.
    """
    failures: dict[str, dict] = {}

    track_dir = Path(f"/tmp/claude-tool-failures-{session_id}")
    if not track_dir.is_dir():
        return failures

    for count_file in sorted(track_dir.glob("*.count")):
        tool_key = count_file.stem  # e.g. "bash"

        # Read failure count
        count = 0
        try:
            raw = count_file.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                count = int(raw)
        except (OSError, ValueError):
            pass

        if count == 0:
            continue

        # Read last exit code and original tool name from the .log file
        log_file = count_file.with_suffix(".log")
        last_exit_code = "unknown"
        tool_name = tool_key

        try:
            if log_file.exists():
                text = log_file.read_text(encoding="utf-8")
                # Recover the canonical tool name from any entry
                m = re.search(r"^tool:\s*(.+)$", text, re.MULTILINE)
                if m:
                    tool_name = m.group(1).strip()

                # Walk entries in reverse order to find the last exit_code
                entries = text.split("---\n")
                for entry in reversed(entries):
                    m = re.search(r"^exit_code:\s*(.+)$", entry, re.MULTILINE)
                    if m:
                        last_exit_code = m.group(1).strip()
                        break
        except OSError:
            pass

        failures[tool_name] = {
            "count": count,
            "last_exit_code": last_exit_code,
        }

    return failures


def create_followup_backlog_items(
    data: ReportData,
    backlog_dir: Path = Path("backlog"),
) -> list[NewBacklogItem]:
    """Create backlog items for failed, paused, and deferred features.

    For each failed/paused feature writes a chore-type backlog item; for each
    deferred feature writes a feature-type backlog item. Tags are inherited
    from the source feature's existing backlog item.

    Args:
        data: Aggregated report data.
        backlog_dir: Directory to write new backlog files into.

    Returns:
        List of NewBacklogItem descriptors for each file written.
    """
    if data.state is None:
        return []

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
        lifecycle_slug = slugify(title)
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
            f"session_id: null\n"
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
        home_repo_name = Path(__file__).resolve().parent.parent.parent.name

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

        # How to try
        verification = _read_verification_strategy(name)
        lines.append("**How to try:**")
        lines.append(verification if verification else "See feature plan for verification steps.")
        lines.append("")

        # Notes from learnings
        learnings = _read_learnings_summary(name)
        if learnings:
            lines.append("**Notes:**")
            lines.append(learnings)
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

    for dq in sorted_deferrals:
        lines.append(f"### {dq.feature}: {dq.question} [{dq.severity}]")
        lines.append(f"> {dq.question}")
        lines.append(f"> Pipeline attempted: {dq.pipeline_attempted}")
        lines.append(f"> Full details: `deferred/{dq.feature}-q{dq.question_id:03d}.md`")

        if dq.severity == SEVERITY_BLOCKING:
            action = "Answer this question and re-run the feature"
        elif dq.severity == SEVERITY_NON_BLOCKING:
            action = "Validate the default choice made during implementation"
        else:
            action = "No action needed — review when convenient"
        lines.append(f"> **To unblock**: {action}")
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

        # Suggested next step
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
    """Collect tool failure data from the session-scoped temp directory.

    Reads ``/tmp/claude-tool-failures-{session_id}/`` for per-tool ``.count``
    and ``.log`` files written by the PostToolUse hook.

    Args:
        session_id: The session identifier used by the hook (may also be a
            date-based fallback key such as ``date-YYYYMMDD``).

    Returns:
        Mapping of tool_key -> ``{"count": int, "last_exit_code": str}`` for
        each tool that has recorded at least one failure.  Returns an empty
        dict when the directory is absent or contains no failure records.
    """
    track_dir = Path(f"/tmp/claude-tool-failures-{session_id}")
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


def render_tool_failures(data: ReportData) -> str:
    """Render the tool failures section.

    Reads ``/tmp/claude-tool-failures-{session_id}/`` for accumulated failure
    data produced by the PostToolUse hook.  The section is omitted entirely
    (returns ``""``) when no failures were recorded, keeping the report clean
    for sessions that ran without Bash tool errors.

    Args:
        data: Aggregated report data.  Uses ``data.session_id`` to locate the
            temp directory.

    Returns:
        A markdown section string listing per-tool failure counts and last exit
        code, or an empty string if there are no failures to report.
    """
    if not data.session_id:
        return ""

    failures = collect_tool_failures(data.session_id)
    if not failures:
        return ""

    total = sum(info["count"] for info in failures.values())
    lines: list[str] = [f"## Tool Failures ({total})", ""]

    for tool_key in sorted(failures):
        info = failures[tool_key]
        count = info["count"]
        lines.append(
            f"- **{tool_key}**: {count} failure{'s' if count != 1 else ''}"
            f" (last exit code: {info['last_exit_code']})"
        )

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


# ---------------------------------------------------------------------------
# Top-level report generation
# ---------------------------------------------------------------------------

def generate_report(data: ReportData) -> str:
    """Assemble the complete morning report from all sections."""
    sections: list[str] = [
        f"# Morning Report: {data.date}",
        "",
        render_executive_summary(data),
        render_completed_features(data),
        render_deferred_questions(data),
        render_failed_features(data),
        render_new_backlog_items(data),
        render_action_checklist(data),
        render_run_statistics(data),
    ]
    # Tool failures section is omitted entirely when there are no failures
    tool_failures_section = render_tool_failures(data)
    if tool_failures_section:
        sections.append(tool_failures_section)
    return "\n".join(sections)


def write_report(
    report: str,
    path: Path = DEFAULT_REPORT_PATH,
) -> Path:
    """Atomically write the morning report to disk.

    Uses temp file + os.replace for safe writes.
    """
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
    state_path: Path = DEFAULT_STATE_PATH,
    events_path: Path = DEFAULT_LOG_PATH,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
    pr_urls: Optional[dict[str, str]] = None,
    report_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Path:
    """Convenience entry point: collect data, generate, write, and notify.

    Called by the bash runner post-loop:
        python3 -c "from claude.overnight.report import generate_and_write_report; generate_and_write_report()"

    Args:
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
            ``project_root / "lifecycle" / "morning-report.md"`` instead
            of the default ``_LIFECYCLE_ROOT / "morning-report.md"``.
    """
    data = collect_report_data(
        state_path=state_path,
        events_path=events_path,
        deferred_dir=deferred_dir,
        results_dir=results_dir,
    )
    data.pr_urls = pr_urls or {}
    data.new_backlog_items = create_followup_backlog_items(data)
    report = generate_report(data)

    # Determine report output path
    report_path: Optional[Path] = None
    if report_dir is not None:
        report_path = report_dir / "morning-report.md"
    elif data.state and data.state.session_id:
        sdir = session_dir(data.state.session_id, lifecycle_root=_LIFECYCLE_ROOT)
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
            project_root / "lifecycle" / "morning-report.md"
            if project_root is not None
            else _LIFECYCLE_ROOT / "morning-report.md"
        )
        try:
            write_report(report, path=latest_copy_path)
        except Exception as exc:  # noqa: BLE001
            print(
                f"warning: failed to write latest-copy to "
                f"{latest_copy_path}: {exc}",
                file=sys.stderr,
            )

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
    return DEFAULT_REPORT_PATH


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

    if args.session:
        sdir = session_dir(args.session, lifecycle_root=_LIFECYCLE_ROOT)
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
    data.new_backlog_items = create_followup_backlog_items(data)
    report = generate_report(data)

    if args.interrupted:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"> **Interrupted Session** — partial report generated at {ts}\n\n"
        report = header + report

    # Determine report output path from session dir
    report_path = None
    if data.state and data.state.session_id:
        sdir = session_dir(data.state.session_id, lifecycle_root=_LIFECYCLE_ROOT)
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
