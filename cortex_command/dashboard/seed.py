"""Dashboard seed script for writing realistic fixture files.

Enables visual testing of every dashboard panel without running a real overnight
workflow. All fixture files are written to their canonical dashboard-polled paths
so the dashboard renders immediately after seeding.

Entry point: python3 -m claude.dashboard.seed
"""

import argparse
import json
import shutil
import sys
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED_PREFIX = "overnight-seed"

# Repo root: seed.py is at claude/dashboard/seed.py, so 2 levels up from here
REPO_ROOT = Path(__file__).resolve().parents[2]

# All timestamps in fixture data are anchored so the session appears to have
# started ~90 minutes ago
SESSION_START_TIME = datetime.now(timezone.utc) - timedelta(minutes=90)

# Session ID derived from current wall-clock time so each run produces a unique
# directory (format: overnight-seed-YYYY-MM-DD-HHMM)
SESSION_ID = f"{SEED_PREFIX}-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')}"

# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def ts_at(minutes_ago: float) -> str:
    """Return an ISO 8601 UTC timestamp for SESSION_START_TIME + offset.

    Args:
        minutes_ago: Minutes before now to compute the timestamp for.
                     0 = current time, 90 = SESSION_START_TIME (session start).
                     Negative values represent times in the future relative to
                     the session start (i.e. later in the session).

    Returns:
        ISO 8601 string with UTC timezone suffix, e.g.
        '2026-02-27T10:30:00+00:00'.
    """
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.isoformat()


# ---------------------------------------------------------------------------
# Feature slugs and pipeline feature names
# ---------------------------------------------------------------------------

FEATURE_SLUGS = [
    "seed-feature-alpha",
    "seed-feature-beta",
    "seed-feature-gamma",
    "seed-feature-delta",
    "seed-feature-epsilon",
]

PIPELINE_FEATURES = [
    "seed-pipeline-feature-one",
    "seed-pipeline-feature-two",
    "seed-pipeline-feature-three",
]

# ---------------------------------------------------------------------------
# Overnight state and events writers
# ---------------------------------------------------------------------------

# Feature definitions: slug -> (status, round_assigned, started_offset, completed_offset, error)
# Offsets are minutes_ago values (higher = further in the past)
_FEATURES = [
    ("seed-feature-alpha", "merged",  88, 75, None),
    ("seed-feature-beta",  "merged",  85, 70, None),
    ("seed-feature-gamma", "running", 40, None, None),
    ("seed-feature-delta", "paused",  60, None, None),
    ("seed-feature-epsilon","failed", 35, 28, "Agent exited with non-zero status"),
]


def _feature_entry(slug: str, status: str, round_assigned: int,
                   started_offset: float, completed_offset, error) -> dict:
    """Build a single feature entry for the overnight state features dict."""
    return {
        "status": status,
        "round_assigned": round_assigned,
        "started_at": ts_at(started_offset),
        "completed_at": ts_at(completed_offset) if completed_offset is not None else None,
        "error": error,
        "deferred_questions": 0,
        "spec_path": f"lifecycle/{slug}/spec.md",
        "plan_path": f"lifecycle/{slug}/plan.md",
        "backlog_id": slug,
    }


def write_overnight_state(session_dir: Path, session_id: str) -> None:
    """Write the overnight state JSON to the session directory and canonical path.

    Writes to:
      {session_dir}/overnight-state.json
      lifecycle/overnight-state.json  (copy via shutil.copy2)
    """
    # Build features dict
    features: dict = {}
    round_assignments = {
        "seed-feature-alpha":   1,
        "seed-feature-beta":    1,
        "seed-feature-gamma":   3,
        "seed-feature-delta":   2,
        "seed-feature-epsilon": 3,
    }
    for slug, status, started_offset, completed_offset, error in _FEATURES:
        features[slug] = _feature_entry(
            slug, status,
            round_assignments[slug],
            started_offset,
            completed_offset,
            error,
        )

    # Round history: 3 entries
    round_history = [
        {
            "round_number": 1,
            "features_attempted": ["seed-feature-alpha", "seed-feature-beta"],
            "features_merged":    ["seed-feature-alpha", "seed-feature-beta"],
            "features_paused":    [],
            "features_deferred":  [],
            "started_at":         ts_at(88),
            "completed_at":       ts_at(65),
        },
        {
            "round_number": 2,
            "features_attempted": ["seed-feature-delta"],
            "features_merged":    [],
            "features_paused":    ["seed-feature-delta"],
            "features_deferred":  [],
            "started_at":         ts_at(64),
            "completed_at":       ts_at(45),
        },
        {
            "round_number": 3,
            "features_attempted": ["seed-feature-gamma", "seed-feature-epsilon"],
            "features_merged":    [],
            "features_paused":    [],
            "features_deferred":  [],
            "started_at":         ts_at(44),
            "completed_at":       None,
        },
    ]

    state = {
        "session_id":         session_id,
        "plan_ref":           "main",
        "current_round":      3,
        "phase":              "executing",
        "started_at":         ts_at(90),
        "updated_at":         ts_at(0),
        "paused_from":        None,
        "integration_branch": f"overnight/{session_id}",
        "features":           features,
        "round_history":      round_history,
    }

    # Write to session directory
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / "overnight-state.json"
    session_path.write_text(json.dumps(state, indent=2))

    # Copy to canonical path (must be a regular file, not a symlink)
    canonical = REPO_ROOT / "lifecycle" / "overnight-state.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # Remove symlink or existing file before copy so shutil.copy2 writes a fresh regular file
    if canonical.exists() or canonical.is_symlink():
        canonical.unlink()
    shutil.copy2(str(session_path), str(canonical))

    print(f"  Wrote {session_path.relative_to(REPO_ROOT)}")
    print(f"  Copied to lifecycle/overnight-state.json")


def write_overnight_events(session_dir: Path, session_id: str) -> None:
    """Write the overnight events JSONL log to the session directory and canonical path.

    Writes to:
      {session_dir}/overnight-events.log
      lifecycle/overnight-events.log  (copy via shutil.copy2)

    Produces 30+ JSONL events covering the full session timeline.
    """
    events = []

    def evt(ts_offset: float, event: str, round_num: int, **extra) -> dict:
        e = {"ts": ts_at(ts_offset), "event": event, "round": round_num}
        e.update(extra)
        return e

    # SESSION_START
    events.append(evt(90, "SESSION_START", 1, session_id=session_id))

    # --- Round 1: alpha + beta ---
    events.append(evt(88, "ROUND_START",     1))
    events.append(evt(87, "BATCH_ASSIGNED",  1,
                       features=["seed-feature-alpha", "seed-feature-beta"]))
    events.append(evt(86, "FEATURE_START",   1, feature="seed-feature-alpha"))
    events.append(evt(85, "FEATURE_START",   1, feature="seed-feature-beta"))
    events.append(evt(78, "FEATURE_COMPLETE",1, feature="seed-feature-alpha", status="merged"))
    events.append(evt(75, "FEATURE_COMPLETE",1, feature="seed-feature-beta",  status="merged"))
    events.append(evt(65, "ROUND_COMPLETE",  1,
                       features_merged=["seed-feature-alpha", "seed-feature-beta"]))

    # --- Round 2: delta ---
    events.append(evt(64, "ROUND_START",    2))
    events.append(evt(63, "BATCH_ASSIGNED", 2, features=["seed-feature-delta"]))
    events.append(evt(62, "FEATURE_START",  2, feature="seed-feature-delta"))
    events.append(evt(55, "FEATURE_PAUSED", 2, feature="seed-feature-delta",
                       reason="Awaiting clarification"))
    events.append(evt(45, "ROUND_COMPLETE", 2,
                       features_merged=[], features_paused=["seed-feature-delta"]))

    # --- Round 3: gamma (running) + epsilon (failed) ---
    events.append(evt(44, "ROUND_START",    3))
    events.append(evt(43, "BATCH_ASSIGNED", 3,
                       features=["seed-feature-gamma", "seed-feature-epsilon"]))
    events.append(evt(42, "FEATURE_START",  3, feature="seed-feature-gamma"))
    events.append(evt(41, "FEATURE_START",  3, feature="seed-feature-epsilon"))

    # epsilon intermediate events before failure
    events.append(evt(38, "FEATURE_CHECKPOINT", 3, feature="seed-feature-epsilon",
                       note="Checkpoint before final step"))
    events.append(evt(35, "FEATURE_RETRY",      3, feature="seed-feature-epsilon",
                       attempt=2))
    events.append(evt(32, "FEATURE_FAILED",     3, feature="seed-feature-epsilon",
                       error="Agent exited with non-zero status"))

    # gamma intermediate events (still running)
    events.append(evt(40, "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 2"))
    events.append(evt(37, "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 4"))
    events.append(evt(30, "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 6"))
    events.append(evt(20, "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 8"))
    events.append(evt(10, "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 10"))
    events.append(evt(5,  "FEATURE_CHECKPOINT", 3, feature="seed-feature-gamma",
                       note="Checkpoint after step 12"))

    # Padding events to ensure >= 30 total
    events.append(evt(85, "PLAN_LOADED",    1, plan_ref="main"))
    events.append(evt(84, "BRANCH_CREATED", 1,
                       branch=f"overnight/{session_id}"))
    events.append(evt(74, "MERGE_STARTED",  1, feature="seed-feature-alpha"))
    events.append(evt(72, "MERGE_STARTED",  1, feature="seed-feature-beta"))
    events.append(evt(60, "BRANCH_SYNCED",  2, branch=f"overnight/{session_id}"))
    events.append(evt(2,  "HEARTBEAT",      3, phase="executing"))

    # Verify we have >= 30 events (assert at development time; no-op at runtime)
    assert len(events) >= 30, f"Expected >= 30 events, got {len(events)}"

    lines = [json.dumps(e) for e in events]
    content = "\n".join(lines) + "\n"

    # Write to session directory
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / "overnight-events.log"
    session_path.write_text(content)

    # Copy to canonical path (must be a regular file, not a symlink)
    canonical = REPO_ROOT / "lifecycle" / "overnight-events.log"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # Remove symlink or existing file before copy so shutil.copy2 writes a fresh regular file
    if canonical.exists() or canonical.is_symlink():
        canonical.unlink()
    shutil.copy2(str(session_path), str(canonical))

    print(f"  Wrote {session_path.relative_to(REPO_ROOT)} ({len(events)} events)")
    print(f"  Copied to lifecycle/overnight-events.log")


# ---------------------------------------------------------------------------
# Pipeline fixtures
# ---------------------------------------------------------------------------


def write_pipeline_fixtures(repo_root: Path) -> None:
    """Write lifecycle/pipeline-state.json and lifecycle/pipeline-events.log."""
    lifecycle_dir = repo_root / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pipeline_state = {
        "phase": "complete",
        "mode": "sequential",
        "base_branch": "main",
        "features": [
            {
                "name": PIPELINE_FEATURES[0],
                "backlog_id": "990",
                "priority": 1,
                "status": "implemented",
            },
            {
                "name": PIPELINE_FEATURES[1],
                "backlog_id": "991",
                "priority": 2,
                "status": "implemented",
            },
            {
                "name": PIPELINE_FEATURES[2],
                "backlog_id": "992",
                "priority": 3,
                "status": "pending",
            },
        ],
        "overlap_analysis": (
            "Features are independent with no shared file paths. "
            "Sequential execution is safe; no merge conflicts anticipated."
        ),
        "created": today,
        "updated": today,
    }

    pipeline_state_path = lifecycle_dir / "pipeline-state.json"
    pipeline_state_path.write_text(json.dumps(pipeline_state, indent=2) + "\n")
    print(f"  wrote {pipeline_state_path.relative_to(repo_root)}")

    # pipeline-events.log: one dispatch_start event per pipeline feature
    events_lines = []
    for i, feature_name in enumerate(PIPELINE_FEATURES):
        event = {
            "ts": ts_at(60 - i * 15),
            "event": "dispatch_start",
            "feature": feature_name,
            "complexity": "complex",
            "criticality": "low",
            "model": "sonnet",
            "max_turns": 20,
            "max_budget_usd": 25.0,
        }
        events_lines.append(json.dumps(event))

    pipeline_events_path = lifecycle_dir / "pipeline-events.log"
    pipeline_events_path.write_text("\n".join(events_lines) + "\n")
    print(f"  wrote {pipeline_events_path.relative_to(repo_root)}")


# ---------------------------------------------------------------------------
# Metrics fixture
# ---------------------------------------------------------------------------


def write_metrics(repo_root: Path) -> None:
    """Write lifecycle/metrics.json with per-feature and aggregate data."""
    lifecycle_dir = repo_root / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()

    # Per-feature entries keyed by slug (dict, not list — matches real file format)
    # seed-feature-alpha has total_duration_s=3600 which is well above the
    # aggregate avg of 1400 to exercise slow-flag detection code paths.
    features: dict = {}
    feature_data = [
        ("seed-feature-alpha",   3600.0, 1, False),
        ("seed-feature-beta",    1800.0, 0, True),
        ("seed-feature-gamma",   1500.0, 0, True),
        ("seed-feature-delta",   1200.0, 1, False),
        ("seed-feature-epsilon", 2400.0, 0, True),
    ]

    for slug, duration, rework, fpa in feature_data:
        features[slug] = {
            "tier": "complex",
            "status": "complete",
            "total_duration_s": duration,
            "phase_durations": {
                "implement_to_review": round(duration * 0.7, 1),
            },
            "task_count": 6,
            "rework_cycles": rework,
            "first_pass_approved": fpa,
        }

    # Aggregates for "complex" tier: n >= 10, avg well below alpha's 3600s
    aggregate_avg = 1400.0
    aggregates = {
        "complex": {
            "n": 12,
            "avg_total_duration_s": aggregate_avg,
            "avg_rework_cycles": 0.25,
            "first_pass_approval_rate": 0.75,
        }
    }

    calibration = {
        "complex": {
            "slow_threshold_s": aggregate_avg * 1.5,
        }
    }

    metrics = {
        "generated_at": generated_at,
        "features": features,
        "aggregates": aggregates,
        "calibration": calibration,
    }

    metrics_path = lifecycle_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"  wrote {metrics_path.relative_to(repo_root)}")


# ---------------------------------------------------------------------------
# Per-feature file writers
# ---------------------------------------------------------------------------


def write_feature_files(repo_root: Path, slug: str, status: str) -> None:
    """Write per-feature lifecycle files for a seeded feature.

    Creates ``lifecycle/{slug}/`` under ``repo_root`` and writes three files:

    - ``agent-activity.jsonl``: 12 events — 5 ``tool_call``/``tool_result``
      pairs for tools Read, Grep, Edit, Bash, Write (10 events), then two
      ``turn_complete`` events.
    - ``events.log``: 3 JSONL events — ``lifecycle_start``, then two
      ``phase_transition`` events (research->specify, specify->implement).
    - ``plan.md``: 6 checkboxes (3 checked ``[x]``, 3 unchecked ``[ ]``).

    Args:
        repo_root: Absolute path to the repository root.
        slug: Feature directory name (e.g. ``"seed-feature-alpha"``).
        status: Feature status string (e.g. ``"running"``, ``"merged"``).
            Accepted but not used in file content — reserved for future use.
    """
    feature_dir = repo_root / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # agent-activity.jsonl — 12 events total
    # 5 tool_call/tool_result pairs (10 events) + 2 turn_complete events.
    # Timestamps spread across the last ~60 minutes of the session.
    # ------------------------------------------------------------------
    tools = ["Read", "Grep", "Edit", "Bash", "Write"]
    call_offsets = [58, 52, 46, 40, 34]
    result_offsets = [57, 51, 45, 39, 33]

    activity_events = []
    for i, tool in enumerate(tools):
        activity_events.append({
            "ts": ts_at(call_offsets[i]),
            "event": "tool_call",
            "tool": tool,
            "input_summary": f"lifecycle/{slug}/spec.md",
        })
        activity_events.append({
            "ts": ts_at(result_offsets[i]),
            "event": "tool_result",
            "tool": tool,
            "success": True,
        })

    # Two turn_complete events (turns 1 and 2)
    activity_events.append({
        "ts": ts_at(20),
        "event": "turn_complete",
        "turn": 1,
        "cost_usd": 0.18,
    })
    activity_events.append({
        "ts": ts_at(5),
        "event": "turn_complete",
        "turn": 2,
        "cost_usd": 0.23,
    })

    activity_path = feature_dir / "agent-activity.jsonl"
    activity_path.write_text(
        "\n".join(json.dumps(e) for e in activity_events) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # events.log — exactly 3 JSONL events
    # Event 1: lifecycle_start
    # Event 2: phase_transition research -> specify
    # Event 3: phase_transition specify -> implement
    # ------------------------------------------------------------------
    events_log = [
        {
            "ts": ts_at(85),
            "event": "lifecycle_start",
            "feature": slug,
            "tier": "complex",
            "criticality": "low",
        },
        {
            "ts": ts_at(70),
            "event": "phase_transition",
            "feature": slug,
            "from": "research",
            "to": "specify",
        },
        {
            "ts": ts_at(45),
            "event": "phase_transition",
            "feature": slug,
            "from": "specify",
            "to": "implement",
        },
    ]

    events_path = feature_dir / "events.log"
    events_path.write_text(
        "\n".join(json.dumps(e) for e in events_log) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # plan.md — 6 checkboxes (3 checked, 3 unchecked)
    # parse_plan_progress() counts [x] and [ ] occurrences.
    # ------------------------------------------------------------------
    plan_content = (
        "- [x] Task 1: Research existing patterns\n"
        "- [x] Task 2: Write spec\n"
        "- [x] Task 3: Implement core function\n"
        "- [ ] Task 4: Add tests\n"
        "- [ ] Task 5: Update justfile\n"
        "- [ ] Task 6: Verify end-to-end\n"
    )

    plan_path = feature_dir / "plan.md"
    plan_path.write_text(plan_content, encoding="utf-8")

    print(f"  Wrote lifecycle/{slug}/{{agent-activity.jsonl,events.log,plan.md}}")


# ---------------------------------------------------------------------------
# Backlog seed items
# ---------------------------------------------------------------------------

# Backlog seed definitions: (number, slug-suffix, status, title)
_BACKLOG_ITEMS = [
    (990, "seed-feature-alpha",   "open",        "Seed: Add authentication to API gateway"),
    (991, "seed-feature-beta",    "in-progress",  "Seed: Migrate database schema to v2"),
    (992, "seed-feature-gamma",   "on-hold",     "Seed: Refactor notification pipeline"),
    (993, "seed-feature-delta",   "refined",     "Seed: Implement rate limiting for export endpoints"),
    (994, "seed-feature-epsilon", "done",        "Seed: Deprecate legacy webhook handler"),
]


def write_backlog_items(repo_root: Path) -> list[Path]:
    """Write 5 seed backlog items to backlog/990-seed-*.md through backlog/994-seed-*.md.

    Each file has YAML frontmatter with ``status`` and ``title`` fields covering
    all status variants: open, in-progress, on-hold, refined, done.

    Args:
        repo_root: Absolute path to the repository root.

    Returns:
        List of Paths that were written.
    """
    backlog_dir = repo_root / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for number, slug, status, title in _BACKLOG_ITEMS:
        filename = f"{number}-{slug}.md"
        content = (
            f"---\n"
            f"title: {title}\n"
            f"status: {status}\n"
            f"---\n"
            f"\n"
            f"Seed backlog item for dashboard visual testing.\n"
        )
        path = backlog_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
        print(f"  wrote backlog/{filename}")

    return written


# ---------------------------------------------------------------------------
# Seed / clean entry points
# ---------------------------------------------------------------------------


def write_all(repo_root: Path, session_id: str) -> None:
    """Write all fixture files: overnight state, events, per-feature files,
    pipeline fixtures, metrics, and backlog items.

    Args:
        repo_root: Absolute path to the repository root.
        session_id: Session ID string for the seed session.
    """
    session_dir = repo_root / "lifecycle" / "sessions" / session_id
    written_paths: list[Path] = []

    write_overnight_state(session_dir, session_id)
    written_paths.append(session_dir / "overnight-state.json")
    written_paths.append(repo_root / "lifecycle" / "overnight-state.json")

    write_overnight_events(session_dir, session_id)
    written_paths.append(session_dir / "overnight-events.log")
    written_paths.append(repo_root / "lifecycle" / "overnight-events.log")

    for slug, status, *_ in _FEATURES:
        write_feature_files(repo_root, slug, status)
        feature_dir = repo_root / "lifecycle" / slug
        written_paths.append(feature_dir / "agent-activity.jsonl")
        written_paths.append(feature_dir / "events.log")
        written_paths.append(feature_dir / "plan.md")

    write_pipeline_fixtures(repo_root)
    written_paths.append(repo_root / "lifecycle" / "pipeline-state.json")
    written_paths.append(repo_root / "lifecycle" / "pipeline-events.log")

    write_metrics(repo_root)
    written_paths.append(repo_root / "lifecycle" / "metrics.json")

    backlog_paths = write_backlog_items(repo_root)
    written_paths.extend(backlog_paths)

    print("\nFiles written:")
    for path in written_paths:
        print(f"  {path.relative_to(repo_root)}")


def run_seed() -> None:
    """Write all fixture files to their canonical locations."""
    print(f"Seeding dashboard fixtures (session: {SESSION_ID}) …")
    write_all(REPO_ROOT, SESSION_ID)
    print("Done.")


def clean_all(repo_root: Path) -> None:
    """Remove all files created by a previous seed run.

    Removal order:
    1. lifecycle/overnight-state.json — only if session_id contains "overnight-seed"
    2. lifecycle/overnight-events.log — only if first line contains "overnight-seed"
    3. lifecycle/sessions/overnight-seed-*/ directories (shutil.rmtree)
    4. lifecycle/seed-feature-*/ directories (shutil.rmtree)
    5. lifecycle/pipeline-state.json
    6. lifecycle/pipeline-events.log
    7. lifecycle/metrics.json
    8. backlog/990-seed-*.md through backlog/994-seed-*.md

    Args:
        repo_root: Absolute path to the repository root.
    """
    removed: list[str] = []
    lifecycle_dir = repo_root / "lifecycle"

    # 1. lifecycle/overnight-state.json — guard: session_id must contain "overnight-seed"
    overnight_state = lifecycle_dir / "overnight-state.json"
    if overnight_state.exists():
        try:
            data = json.loads(overnight_state.read_text(encoding="utf-8"))
            session_id = data.get("session_id", "")
            if "overnight-seed" in session_id:
                overnight_state.unlink()
                removed.append("lifecycle/overnight-state.json")
            else:
                print(
                    f"  WARNING: lifecycle/overnight-state.json has session_id={session_id!r}"
                    " — not a seed file, skipping."
                )
        except Exception as exc:
            print(f"  WARNING: could not parse lifecycle/overnight-state.json ({exc}), skipping.")

    # 2. lifecycle/overnight-events.log — guard: first line must contain "overnight-seed"
    overnight_events = lifecycle_dir / "overnight-events.log"
    if overnight_events.exists():
        try:
            first_line = overnight_events.read_text(encoding="utf-8").splitlines()[0]
            if "overnight-seed" in first_line:
                overnight_events.unlink()
                removed.append("lifecycle/overnight-events.log")
            else:
                print(
                    "  WARNING: lifecycle/overnight-events.log first line does not contain"
                    " 'overnight-seed' — not a seed file, skipping."
                )
        except Exception as exc:
            print(f"  WARNING: could not read lifecycle/overnight-events.log ({exc}), skipping.")

    # 3. lifecycle/sessions/overnight-seed-*/ directories
    sessions_dir = lifecycle_dir / "sessions"
    for session_dir in sessions_dir.glob("overnight-seed-*/"):
        shutil.rmtree(session_dir)
        removed.append(f"lifecycle/sessions/{session_dir.name}/")

    # 4. lifecycle/seed-feature-*/ directories
    for feature_dir in lifecycle_dir.glob("seed-feature-*/"):
        shutil.rmtree(feature_dir)
        removed.append(f"lifecycle/{feature_dir.name}/")

    # 5. lifecycle/pipeline-state.json
    with suppress(FileNotFoundError):
        (lifecycle_dir / "pipeline-state.json").unlink()
        removed.append("lifecycle/pipeline-state.json")

    # 6. lifecycle/pipeline-events.log
    with suppress(FileNotFoundError):
        (lifecycle_dir / "pipeline-events.log").unlink()
        removed.append("lifecycle/pipeline-events.log")

    # 7. lifecycle/metrics.json
    with suppress(FileNotFoundError):
        (lifecycle_dir / "metrics.json").unlink()
        removed.append("lifecycle/metrics.json")

    # 8. backlog/990-seed-*.md through backlog/994-seed-*.md
    backlog_dir = repo_root / "backlog"
    for prefix in range(990, 995):
        for path in backlog_dir.glob(f"{prefix}-seed-*.md"):
            with suppress(FileNotFoundError):
                path.unlink()
                removed.append(f"backlog/{path.name}")

    # Summary
    if removed:
        print("\nRemoved:")
        for item in removed:
            print(f"  {item}")
    else:
        print("  Nothing to remove.")


def run_clean() -> None:
    """Remove all files created by a previous seed run."""
    print("Cleaning seed fixture files …")
    clean_all(REPO_ROOT)
    print("Done.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch to seed or clean."""
    parser = argparse.ArgumentParser(
        prog="python3 -m claude.dashboard.seed",
        description=(
            "Write realistic fixture files for the monitoring dashboard, "
            "enabling visual testing without running a real overnight workflow."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all files previously written by the seed script.",
    )
    args = parser.parse_args()

    if args.clean:
        run_clean()
    else:
        run_seed()


if __name__ == "__main__":
    main()
