"""Dashboard seed script for writing realistic fixture files.

Enables visual testing of every dashboard panel without running a real overnight
workflow. Fixtures are written under an isolated per-user fixture root — never
the operator's own repository — at their canonical dashboard-polled paths, so
``cortex dashboard --root <fixture root>`` renders them immediately.

Entry point: python3 -m cortex_command.dashboard.seed
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cortex_command import common as _common

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED_PREFIX = "overnight-seed"

#: Marker file written inside the fixture root's ``.claude/`` directory. The
#: dashboard's lifespan refuses to start against a root with no ``.claude/``
#: (``app.py`` "Dashboard lifecycle root appears wrong"), so the directory is
#: load-bearing; the marker gives the cleaner a content signal so it can prune
#: ``.claude/`` only when the seeder is the sole thing that put anything there.
SEED_MARKER_NAME = ".dashboard-seed-marker"


# ---------------------------------------------------------------------------
# Fixture root resolution
# ---------------------------------------------------------------------------


def _resolve_fixture_root() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/dashboard-seed``.

    Resolved fresh on each call so tests can redirect ``XDG_STATE_HOME`` via
    ``monkeypatch`` without any module-level caching — mirroring
    ``cortex_command/init/install_state.py``.
    """
    return (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
        / "cortex-command"
        / "dashboard-seed"
    )


def write_seed_marker(root: Path) -> Path:
    """Create ``<root>/.claude/`` with the seed marker file and return its path.

    The dashboard's startup guard requires a ``.claude/`` directory under the
    root it serves, so the fixture root needs one. The marker file inside makes
    the directory identifiable as seeder-created: an operator who points
    ``--root`` at a real repository must never lose their own ``.claude/``.
    """
    marker_dir = root / ".claude"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / SEED_MARKER_NAME
    marker.write_text(
        "Created by cortex-dashboard-seed to satisfy the dashboard's root check.\n",
        encoding="utf-8",
    )
    return marker

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
    "seed-feature-zeta",
]

PIPELINE_FEATURES = [
    "seed-pipeline-feature-one",
    "seed-pipeline-feature-two",
    "seed-pipeline-feature-three",
]

# ---------------------------------------------------------------------------
# Overnight state and events writers
# ---------------------------------------------------------------------------

# Feature definitions: slug -> (status, started_offset, completed_offset, error)
# Offsets are minutes_ago values (higher = further in the past)
#
# ``deferred`` is the overnight *run outcome*, not a backlog frontmatter state:
# it has dedicated rendering (``app.py`` ``badge-amber``/``⚠``) that no other
# fixture reaches, and no backlog record can express it — hence the sixth slug
# rather than a status swap on an existing one.
_FEATURES = [
    ("seed-feature-alpha", "merged",  88, 75, None),
    ("seed-feature-beta",  "merged",  85, 70, None),
    ("seed-feature-gamma", "running", 40, None, None),
    ("seed-feature-delta", "paused",  60, None, None),
    ("seed-feature-epsilon","failed", 35, 28, "Agent exited with non-zero status"),
    ("seed-feature-zeta",  "deferred", 43, 25, None),
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
        "spec_path": f"cortex/lifecycle/{slug}/spec.md",
        "plan_path": f"cortex/lifecycle/{slug}/plan.md",
        "backlog_id": slug,
    }


def write_overnight_state(root: Path, session_dir: Path, session_id: str) -> None:
    """Write the overnight state JSON to the session directory and canonical path.

    Writes to:
      {session_dir}/overnight-state.json
      {root}/cortex/lifecycle/overnight-state.json  (copy via shutil.copy2)

    Args:
        root: Absolute path to the fixture root every path is written under.
        session_dir: Session directory for this seed run (under ``root``).
        session_id: Session ID string for the seed session.
    """
    # Build features dict
    features: dict = {}
    round_assignments = {
        "seed-feature-alpha":   1,
        "seed-feature-beta":    1,
        "seed-feature-gamma":   3,
        "seed-feature-delta":   2,
        "seed-feature-epsilon": 3,
        "seed-feature-zeta":    3,
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
            "features_attempted": [
                "seed-feature-gamma",
                "seed-feature-epsilon",
                "seed-feature-zeta",
            ],
            "features_merged":    [],
            "features_paused":    [],
            "features_deferred":  ["seed-feature-zeta"],
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
    canonical = root / "cortex" / "lifecycle" / "overnight-state.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # Remove symlink or existing file before copy so shutil.copy2 writes a fresh regular file
    if canonical.exists() or canonical.is_symlink():
        canonical.unlink()
    shutil.copy2(str(session_path), str(canonical))

    print(f"  Wrote {session_path.relative_to(root)}")
    print(f"  Copied to cortex/lifecycle/overnight-state.json")


def write_overnight_events(root: Path, session_dir: Path, session_id: str) -> None:
    """Write the overnight events JSONL log to the session directory and canonical path.

    Writes to:
      {session_dir}/overnight-events.log
      {root}/cortex/lifecycle/overnight-events.log  (copy via shutil.copy2)

    Produces 30+ JSONL events covering the full session timeline.

    Args:
        root: Absolute path to the fixture root every path is written under.
        session_dir: Session directory for this seed run (under ``root``).
        session_id: Session ID string for the seed session.
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
                       features=["seed-feature-gamma", "seed-feature-epsilon",
                                 "seed-feature-zeta"]))
    events.append(evt(42, "FEATURE_START",  3, feature="seed-feature-gamma"))
    events.append(evt(41, "FEATURE_START",  3, feature="seed-feature-epsilon"))
    events.append(evt(40, "FEATURE_START",  3, feature="seed-feature-zeta"))

    # zeta is deferred rather than merged, paused, or failed — the one run
    # outcome with no backlog-frontmatter equivalent.
    events.append(evt(25, "FEATURE_DEFERRED", 3, feature="seed-feature-zeta",
                       reason="Deferred to a later round: depends on gamma landing"))

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
    canonical = root / "cortex" / "lifecycle" / "overnight-events.log"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # Remove symlink or existing file before copy so shutil.copy2 writes a fresh regular file
    if canonical.exists() or canonical.is_symlink():
        canonical.unlink()
    shutil.copy2(str(session_path), str(canonical))

    print(f"  Wrote {session_path.relative_to(root)} ({len(events)} events)")
    print(f"  Copied to cortex/lifecycle/overnight-events.log")


# ---------------------------------------------------------------------------
# Pipeline fixtures
# ---------------------------------------------------------------------------


#: Backlog fixture each pipeline feature claims to implement, by slug. The
#: ``backlog_id`` written into ``pipeline-state.json`` is looked up from
#: ``_BACKLOG_ITEMS`` through this map rather than written as a literal, so a
#: renumbered fixture can never leave the pipeline state pointing at an id no
#: backlog file carries.
_PIPELINE_BACKLOG_SLUGS = {
    "seed-pipeline-feature-one":   "seed-feature-alpha",
    "seed-pipeline-feature-two":   "seed-feature-beta",
    "seed-pipeline-feature-three": "seed-feature-gamma",
}


def _backlog_id_for_slug(slug: str) -> str:
    """Return the zero-padded id of the ``_BACKLOG_ITEMS`` record for ``slug``.

    Raises ``KeyError`` rather than inventing an id, so a slug that leaves the
    fixture table fails loudly at seed time instead of writing a dangling
    reference.
    """
    for record in _BACKLOG_ITEMS:
        if record["slug"] == slug:
            return f"{record['id']:03d}"
    raise KeyError(f"No backlog fixture declares slug {slug!r}")


def write_pipeline_fixtures(repo_root: Path) -> None:
    """Write cortex/lifecycle/pipeline-state.json and cortex/lifecycle/pipeline-events.log."""
    lifecycle_dir = repo_root / "cortex" / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pipeline_statuses = ["implemented", "implemented", "pending"]
    pipeline_state = {
        "phase": "complete",
        "mode": "sequential",
        "base_branch": "main",
        "features": [
            {
                "name": name,
                "backlog_id": _backlog_id_for_slug(_PIPELINE_BACKLOG_SLUGS[name]),
                "priority": i + 1,
                "status": pipeline_statuses[i],
            }
            for i, name in enumerate(PIPELINE_FEATURES)
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

    # pipeline-events.log: dispatch_start events for both the 3 pipeline
    # features (varied models/complexities/budgets) and the 5 overnight seed
    # features (so the dashboard's feature_models lookup populates).
    pipeline_variants = [
        ("opus",   "complex", 25.0),
        ("sonnet", "simple",  10.0),
        ("haiku",  "trivial",  5.0),
    ]
    events_lines = []
    for i, feature_name in enumerate(PIPELINE_FEATURES):
        model, complexity, budget = pipeline_variants[i]
        event = {
            "ts": ts_at(60 - i * 15),
            "event": "dispatch_start",
            "feature": feature_name,
            "complexity": complexity,
            "criticality": "low",
            "model": model,
            "max_turns": 20,
            "max_budget_usd": budget,
        }
        events_lines.append(json.dumps(event))

    # Per-seed-feature dispatch_start events (one per slug) so the dashboard's
    # feature_models lookup can resolve each seed feature.
    seed_dispatch_variants = {
        "seed-feature-alpha":   ("opus",   "complex", 25.0),
        "seed-feature-beta":    ("sonnet", "simple",  10.0),
        "seed-feature-gamma":   ("opus",   "complex", 25.0),
        "seed-feature-delta":   ("sonnet", "complex", 25.0),
        "seed-feature-epsilon": ("haiku",  "trivial",  5.0),
        "seed-feature-zeta":    ("sonnet", "simple",  10.0),
    }
    seed_offsets = {
        "seed-feature-alpha":   88,
        "seed-feature-beta":    85,
        "seed-feature-gamma":   42,
        "seed-feature-delta":   62,
        "seed-feature-epsilon": 41,
        "seed-feature-zeta":    40,
    }
    for slug, (model, complexity, budget) in seed_dispatch_variants.items():
        event = {
            "ts": ts_at(seed_offsets[slug]),
            "event": "dispatch_start",
            "feature": slug,
            "complexity": complexity,
            "criticality": "low",
            "model": model,
            "max_turns": 20,
            "max_budget_usd": budget,
        }
        events_lines.append(json.dumps(event))

    pipeline_events_path = lifecycle_dir / "pipeline-events.log"
    pipeline_events_path.write_text("\n".join(events_lines) + "\n")
    print(f"  wrote {pipeline_events_path.relative_to(repo_root)}")


# ---------------------------------------------------------------------------
# Metrics fixture
# ---------------------------------------------------------------------------


def write_metrics(repo_root: Path) -> None:
    """Write cortex/lifecycle/metrics.json with per-feature and aggregate data."""
    lifecycle_dir = repo_root / "cortex" / "lifecycle"
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
        ("seed-feature-zeta",     900.0, 0, True),
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

#: Reader-renderable lifecycle prose, keyed by slug. Only the feature a backlog
#: fixture links to through ``lifecycle_slug`` needs these, so this is a lookup
#: rather than something every feature gets — the same per-feature-variance
#: pattern ``_FEATURE_TIER`` and ``_FEATURE_ESCALATIONS`` use. Each body is
#: ``##``-sectioned markdown so the ticket reader has real structure to render
#: rather than a placeholder line.
_FEATURE_ARTIFACTS = {
    "seed-feature-delta": {
        "research.md": """\
# Research: Implement rate limiting for export endpoints

## Problem

The export endpoints share a process-wide connection pool with the rest of the
API, so a single client draining a bulk export starves interactive traffic. No
limit is enforced today; the only backpressure is the pool timeout, which
surfaces to callers as an opaque 500.

## Prior Art

Two shapes exist in the codebase already. The webhook handler retries on a
fixed interval with no server-side limit, and the ingest path caps concurrency
with a semaphore rather than a rate. Neither generalizes: a semaphore bounds
in-flight work but not request volume, and client-side retry cannot protect a
shared pool from a client that ignores it.

## Options Considered

- **Per-endpoint token bucket** — each export route gets its own budget.
  Isolates a hot route, but a client fanning across routes still saturates the
  pool.
- **Global rolling window** — one shared quota across the API surface. Protects
  the pool directly, at the cost of letting one noisy route consume everything.
- **Hybrid** — a global ceiling with per-endpoint floors. Strictly better
  behavior, materially more state to maintain and reason about.

## Open Questions

Whether export endpoints draw from the same quota as the rest of the API is
unresolved, and the spec's own section 3.2 reads both ways. That ambiguity is
what the escalation on this feature is about.
""",
        "spec.md": """\
# Specification: Implement rate limiting for export endpoints

## Problem Statement

Bulk export requests share the API's connection pool with interactive traffic
and are subject to no volume limit, so one client can starve every other caller
until the pool times out.

## Requirements

1. **Export routes enforce a request-rate limit.** Requests beyond the limit
   receive `429` rather than queuing against the pool.
2. **The limit is observable.** Each response carries the remaining budget, so
   a well-behaved client can pace itself without probing for the ceiling.
3. **Rejections are retryable on a stated schedule** rather than leaving the
   backoff strategy to each client's guess.

## Edge Cases

- **Clock skew across workers** — buckets refill against a monotonic source,
  not wall time, so a skewed worker cannot hand out a larger budget.
- **In-flight requests at a limit change** — a config reload never revokes
  budget already granted; the new ceiling applies from the next refill.

## Open Decisions

Whether the quota is per-endpoint or shared across the API surface. Section 3.2
of the source ticket references both, and the acceptance scaffolding assumes
the opposite of what the plan task does — escalated rather than guessed.
""",
    },
}


def write_feature_artifacts(repo_root: Path, slug: str) -> list[str]:
    """Write the reader-renderable lifecycle artifacts declared for ``slug``.

    Returns the filenames written — empty for a feature with no entry in
    ``_FEATURE_ARTIFACTS``.
    """
    artifacts = _FEATURE_ARTIFACTS.get(slug)
    if not artifacts:
        return []

    feature_dir = repo_root / "cortex" / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    for name, body in artifacts.items():
        (feature_dir / name).write_text(body, encoding="utf-8")
    return list(artifacts)


def write_feature_files(repo_root: Path, slug: str, status: str) -> None:
    """Write per-feature lifecycle files for a seeded feature.

    Creates ``cortex/lifecycle/{slug}/`` under ``repo_root`` and writes three files:

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
    feature_dir = repo_root / "cortex" / "lifecycle" / slug
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
            "input_summary": f"cortex/lifecycle/{slug}/spec.md",
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
    # The canonical detector (cortex_command.common.detect_lifecycle_phase)
    # counts **Status**: [x] / [ ] occurrences for plan progress.
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

    print(f"  Wrote cortex/lifecycle/{slug}/{{agent-activity.jsonl,events.log,plan.md}}")


# ---------------------------------------------------------------------------
# Extended per-feature fixtures (escalations, exit-reports,
# learnings, enriched events.log) — added for the new dashboard panels.
# ---------------------------------------------------------------------------

# Per-feature tier and clarify_critic findings_count assignments.
# Vary findings_count so some features show "clean clarify" (count=0).
_FEATURE_TIER = {
    "seed-feature-alpha":   "complex",
    "seed-feature-beta":    "simple",
    "seed-feature-gamma":   "complex",
    "seed-feature-delta":   "complex",
    "seed-feature-epsilon": "trivial",
    "seed-feature-zeta":    "simple",
}

_FEATURE_CLARIFY_FINDINGS = {
    "seed-feature-alpha":   3,
    "seed-feature-beta":    0,  # clean clarify
    "seed-feature-gamma":   5,
    "seed-feature-delta":   9,
    "seed-feature-epsilon": 1,
    "seed-feature-zeta":    2,
}

# PR numbers for merged features
_FEATURE_PR_NUMBER = {
    "seed-feature-alpha": 421,
    "seed-feature-beta":  422,
}

# Deterministic dispatch IDs per feature (uuid hex) so reruns produce diffs
# only when content actually changes.
_FEATURE_DISPATCH_IDS = {
    "seed-feature-alpha":   uuid.UUID("11111111-1111-4111-8111-111111111111").hex,
    "seed-feature-beta":    uuid.UUID("22222222-2222-4222-8222-222222222222").hex,
    "seed-feature-gamma":   uuid.UUID("33333333-3333-4333-8333-333333333333").hex,
    "seed-feature-delta":   uuid.UUID("44444444-4444-4444-8444-444444444444").hex,
    "seed-feature-epsilon": uuid.UUID("55555555-5555-4555-8555-555555555555").hex,
    "seed-feature-zeta":    uuid.UUID("66666666-6666-4666-8666-666666666666").hex,
}

# Escalation question/context pairs for the paused (delta) and failed (epsilon)
# features. Each entry produces one escalation jsonl line.
_FEATURE_ESCALATIONS = {
    "seed-feature-delta": [
        {
            "question": (
                "Should I implement variant A (per-endpoint token bucket) or variant B "
                "(global rolling window) given the spec ambiguity around how export "
                "endpoints share the rate-limit quota with the rest of the API?"
            ),
            "context": (
                "Spec section 3.2 references both 'per-endpoint' and 'shared pool' "
                "limits in adjacent paragraphs without disambiguating. The plan "
                "task assumed variant A but the acceptance test scaffolding "
                "appears to assert variant B."
            ),
            "round": 2,
        },
        {
            "question": (
                "The retry budget for 429 responses isn't specified — should "
                "downstream clients receive Retry-After headers or rely on "
                "exponential backoff?"
            ),
            "context": (
                "Existing webhook handler uses fixed-interval retries; if we "
                "diverge that breaks the contract documented in docs/api.md."
            ),
            "round": 2,
        },
    ],
    "seed-feature-epsilon": [
        {
            "question": (
                "The Bash tool sandbox failed to initialize on the third retry — "
                "should I bypass the sandbox for this specific deprecation script, "
                "or roll back the change?"
            ),
            "context": (
                "Sandbox seatbelt-probe reports 'Operation not permitted' on the "
                "legacy webhook handler's tmp directory. Running unsandboxed would "
                "violate the MCP-unsandboxed framing policy without explicit user "
                "consent."
            ),
            "round": 3,
        },
    ],
}


def write_escalations(repo_root: Path, slug: str) -> bool:
    """Write escalations.jsonl for features that have escalations defined.

    Returns True if a file was written, False if the feature has no escalations.
    """
    escalations = _FEATURE_ESCALATIONS.get(slug)
    if not escalations:
        return False

    feature_dir = repo_root / "cortex" / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    for i, esc in enumerate(escalations, start=1):
        round_num = esc["round"]
        entry = {
            "type": "escalation",
            "escalation_id": f"{slug}-r{round_num}-q{i}",
            "session_id": SESSION_ID,
            "feature": slug,
            "round": round_num,
            "question": esc["question"],
            "context": esc["context"],
            "ts": ts_at(50 - i * 5),
        }
        lines.append(json.dumps(entry))

    path = feature_dir / "escalations.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote cortex/lifecycle/{slug}/escalations.jsonl ({len(lines)} entries)")
    return True


def write_exit_reports(repo_root: Path, slug: str, status: str) -> int:
    """Write per-plan-task exit-reports/{n}.json files for a feature.

    Returns the number of report files written.
    """
    feature_dir = repo_root / "cortex" / "lifecycle" / slug
    exit_dir = feature_dir / "exit-reports"
    exit_dir.mkdir(parents=True, exist_ok=True)

    # Per-feature task descriptions for realistic-sounding reasons
    task_reasons = {
        "seed-feature-alpha": [
            "Researched existing auth middleware patterns in api/gateway/",
            "Drafted JWT validation spec with refresh-token rotation",
            "Implemented token validation middleware and wired into routes",
            "Added integration tests covering expired/revoked tokens",
            "Updated justfile recipe and docs/auth.md",
            "Verified end-to-end with curl smoke test against staging",
        ],
        "seed-feature-beta": [
            "Audited current schema usage across services",
            "Wrote migration plan with backfill strategy",
            "Implemented Alembic migration scripts for v2 tables",
            "Added rollback fixtures and dry-run integration test",
            "Updated ORM models and dependent query helpers",
        ],
        "seed-feature-gamma": [
            "Mapped existing notification fan-out paths",
            "Drafted refactor spec with adapter interface",
            "Extracted publisher adapter and migrated email path",
        ],
        "seed-feature-delta": [
            "Surveyed rate-limit libraries (slowapi, fastapi-limiter)",
            "Drafted spec covering per-endpoint and shared-pool variants",
            "Implemented token-bucket middleware skeleton",
        ],
        "seed-feature-epsilon": [
            "Identified all callers of legacy webhook handler",
            "Removed handler module and updated routing table",
        ],
        "seed-feature-zeta": [
            "Catalogued the CSV export paths the timeline view would reuse",
            "Drafted spec for the multi-repo fleet roll-up",
        ],
    }

    tasks = task_reasons.get(slug, [])
    reports = []

    if status == "merged":
        # All complete
        for i, reason in enumerate(tasks, start=1):
            reports.append({
                "task_number": i,
                "action": "complete",
                "reason": reason,
                "ts": ts_at(80 - i * 2),
            })
    elif status == "paused":
        # Early tasks complete, blocking task is "question"
        for i, reason in enumerate(tasks, start=1):
            if i < len(tasks):
                reports.append({
                    "task_number": i,
                    "action": "complete",
                    "reason": reason,
                    "ts": ts_at(60 - i * 2),
                })
            else:
                reports.append({
                    "task_number": i,
                    "action": "question",
                    "reason": "Blocked on spec ambiguity for rate-limit scope",
                    "question": (
                        "Should rate limits be per-endpoint or pool-shared? "
                        "Spec section 3.2 references both."
                    ),
                    "ts": ts_at(55),
                })
    elif status == "failed":
        # Early tasks complete, last task failed
        for i, reason in enumerate(tasks, start=1):
            if i < len(tasks):
                reports.append({
                    "task_number": i,
                    "action": "complete",
                    "reason": reason,
                    "ts": ts_at(38 - i * 2),
                })
            else:
                reports.append({
                    "task_number": i,
                    "action": "failed",
                    "reason": "Agent exited with non-zero status during execution",
                    "error": (
                        "task_failure: ProcessError: Command failed with exit "
                        "code 1 (exit code: 1)"
                    ),
                    "ts": ts_at(32),
                })
    else:
        # running (gamma) — write the completed tasks so far, no terminal report
        for i, reason in enumerate(tasks, start=1):
            reports.append({
                "task_number": i,
                "action": "complete",
                "reason": reason,
                "ts": ts_at(40 - i * 3),
            })

    for i, report in enumerate(reports, start=1):
        path = exit_dir / f"{i}.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"  wrote cortex/lifecycle/{slug}/exit-reports/ ({len(reports)} reports)")
    return len(reports)


def write_learnings_progress(repo_root: Path, slug: str, status: str) -> bool:
    """Write learnings/progress.txt for failed and paused features.

    Returns True if a file was written.
    """
    if status not in ("failed", "paused"):
        return False

    feature_dir = repo_root / "cortex" / "lifecycle" / slug
    learnings_dir = feature_dir / "learnings"
    learnings_dir.mkdir(parents=True, exist_ok=True)

    if status == "failed":
        attempts = [
            {
                "ts": ts_at(36),
                "task": "Remove legacy webhook handler and update routing table",
                "error": "task_failure: ProcessError: Command failed with exit code 1 (exit code: 1)",
                "output": "Check stderr output for details",
            },
            {
                "ts": ts_at(34),
                "task": "Remove legacy webhook handler and update routing table",
                "error": "task_failure: ProcessError: Command failed with exit code 1 (exit code: 1)",
                "output": "Check stderr output for details",
            },
            {
                "ts": ts_at(32),
                "task": "Remove legacy webhook handler and update routing table",
                "error": "task_failure: ProcessError: Sandbox initialization failed",
                "output": "Operation not permitted on tmp directory",
            },
        ]
    else:  # paused
        attempts = [
            {
                "ts": ts_at(58),
                "task": "Implement token-bucket middleware for export endpoints",
                "error": "task_failure: SpecAmbiguity: per-endpoint vs shared-pool unresolved",
                "output": "Halted before writing middleware module",
            },
            {
                "ts": ts_at(55),
                "task": "Escalate spec ambiguity for rate-limit scope",
                "error": "task_failure: AwaitingClarification: blocked on user input",
                "output": "Escalation written to escalations.jsonl",
            },
        ]

    lines = [""]
    for i, att in enumerate(attempts, start=1):
        lines.append("============================================================")
        lines.append(f"Attempt {i} | {att['ts']}")
        lines.append("============================================================")
        lines.append(f"Task: {att['task']}")
        lines.append(f"Error: {att['error']}")
        lines.append(f"Output:")
        lines.append(att["output"])
        lines.append("")

    path = learnings_dir / "progress.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote cortex/lifecycle/{slug}/learnings/progress.txt ({len(attempts)} attempts)")
    return True


def write_enriched_events_log(repo_root: Path, slug: str, status: str) -> None:
    """Rewrite events.log with enriched prepended events.

    Replaces the basic 3-event events.log produced by write_feature_files()
    with a richer event stream including clarify_critic, complexity_override
    (delta only), lifecycle_start with tier/criticality, phase_transitions,
    and (for merged) spec_approved / plan_approved / dispatch_complete.
    """
    feature_dir = repo_root / "cortex" / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)

    tier = _FEATURE_TIER[slug]
    findings = _FEATURE_CLARIFY_FINDINGS[slug]
    # dispositions: roughly findings split into apply/dismiss with at most a
    # small number of asks; for findings=0 all zero.
    if findings == 0:
        apply_n, dismiss_n, ask_n = 0, 0, 0
    else:
        apply_n = max(1, findings * 2 // 3)
        dismiss_n = findings - apply_n
        ask_n = 0
    applied_fixes = apply_n
    dismissals = dismiss_n

    events: list[dict] = []

    # 1. clarify_critic
    events.append({
        "schema_version": 3,
        "ts": ts_at(86),
        "event": "clarify_critic",
        "feature": slug,
        "parent_epic_loaded": False,
        "findings_count": findings,
        "dispositions": {"apply": apply_n, "dismiss": dismiss_n, "ask": ask_n},
        "applied_fixes_count": applied_fixes,
        "dismissals_count": dismissals,
        "status": "ok",
    })

    # 2. complexity_override — delta only
    if slug == "seed-feature-delta":
        events.append({
            "schema_version": 3,
            "ts": ts_at(85.5),
            "event": "complexity_override",
            "feature": slug,
            "from": "simple",
            "to": "complex",
            "gate": "specify_open_decisions",
            "note": (
                "Spec uncovered conflicting rate-limit semantics (per-endpoint "
                "vs shared-pool); requires complex-tier deliberation."
            ),
        })

    # 3. lifecycle_start
    events.append({
        "ts": ts_at(85),
        "event": "lifecycle_start",
        "feature": slug,
        "tier": tier,
        "criticality": "low",
    })

    # 4. existing phase_transitions
    events.append({
        "ts": ts_at(70),
        "event": "phase_transition",
        "feature": slug,
        "from": "research",
        "to": "specify",
    })
    events.append({
        "ts": ts_at(45),
        "event": "phase_transition",
        "feature": slug,
        "from": "specify",
        "to": "implement",
    })

    # 5. merged-only: spec_approved, plan_approved, dispatch_complete
    if status == "merged":
        pr_num = _FEATURE_PR_NUMBER[slug]
        events.append({
            "ts": ts_at(82),
            "event": "spec_approved",
            "feature": slug,
        })
        events.append({
            "ts": ts_at(80),
            "event": "plan_approved",
            "feature": slug,
        })
        events.append({
            "ts": ts_at(75),
            "event": "dispatch_complete",
            "feature": slug,
            "outcome": "merged",
            "pr_url": f"https://github.com/example/repo/pull/{pr_num}",
        })

    path = feature_dir / "events.log"
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    print(f"  rewrote cortex/lifecycle/{slug}/events.log ({len(events)} events)")


# ---------------------------------------------------------------------------
# Backlog seed items
# ---------------------------------------------------------------------------

#: The tag every fixture carries and the prefix every fixture title starts
#: with. Both are applied by the renderer rather than repeated in the table, so
#: a record cannot be added without them: the feed side does no filtering at
#: all, and self-identification is the only thing separating fixtures from real
#: work in a corpus that renders them identically.
SEED_TAG = "dashboard-seed"
SEED_TITLE_PREFIX = "Seed: "

_DEFAULT_BODY = (
    "Seed backlog item for dashboard visual testing, written by\n"
    "`cortex-dashboard-seed` into an isolated fixture root — never a real backlog.\n"
)

#: The epic fixture's body. Its children are listed in prose as well as being
#: reachable through each child's ``parent`` field, so a view that renders
#: markdown and a view that walks the epic map both have something to show.
_EPIC_BODY = """\
## Summary

Umbrella item for the command-station dashboard. The board reads its children
through the epic map; this body states them literally so the reader has the
same fact without a second lookup.

## Children

- 007 — board columns for the command station
- 008 — ticket reader for the command station
"""

#: The one fixture body that exercises the full markdown pipeline. The reader
#: enables only ``fenced_code`` and ``tables``, so a body carrying headings, a
#: fenced block, and a pipe table covers every extension actually turned on.
_RICH_BODY = """\
## Context

The reader renders item bodies with only the `fenced_code` and `tables`
markdown extensions enabled. This body exercises both, plus headings, so a
rendering regression in any of the three shows up against the seeded corpus.

## Approach

```python
def render(item: dict) -> str:
    # Render one ticket body through the dashboard's markdown pipeline.
    return markdown.markdown(item["body"], extensions=["fenced_code", "tables"])
```

## Trade-offs

| Option | Render cost | Fidelity |
|---|---|---|
| Raw text | none | none |
| Fenced code only | low | partial |
| Fenced code and tables | low | full |
"""

# Backlog fixture records. Required keys — ``id``, ``slug``, ``status``,
# ``priority``, ``type``, ``title`` — are on every record; every other key is
# optional and is emitted only when a record declares it, never as an empty
# scalar. Optional keys: ``areas``, ``parent``, ``blocked_by``,
# ``lifecycle_slug``, ``spec``, ``extra_tags``, ``body``, ``archived``.
#
# The roster is a coverage matrix, not a sample: between them these records
# carry an epic with children, a CLOSED epic with a still-active child, a child
# pointing at a non-epic parent, a terminal status, all four blocker outcomes
# (internal non-terminal, internal terminal, external, and not-found), both
# deferral vocabularies, a resolvable lifecycle slug, a deliberately
# unresolvable one, and an archived id.
#
# IDs are ordinary low numbers: fixtures reach no real backlog any more, so
# nothing needs a reserved band to stay out of an allocator's way.
_BACKLOG_ITEMS: list[dict] = [
    # 001 — the non-epic parent 009 points at, and the only record with areas.
    {
        "id": 1,
        "slug": "seed-feature-alpha",
        "status": "backlog",
        "priority": "medium",
        "type": "feature",
        "title": "Add authentication to API gateway",
        "areas": ["dashboard", "docs"],
    },
    # 002 — non-terminal blocker target for 007.
    {
        "id": 2,
        "slug": "seed-feature-beta",
        "status": "in_progress",
        "priority": "high",
        "type": "feature",
        "title": "Migrate database schema to v2",
    },
    # 003 — terminal status: present on disk, filtered out of active items.
    {
        "id": 3,
        "slug": "seed-feature-gamma",
        "status": "abandoned",
        "priority": "low",
        "type": "chore",
        "title": "Refactor notification pipeline",
    },
    # 004 — the one fixture whose lifecycle_slug resolves to a real directory,
    # which is what gives the snapshot a non-null phase to report.
    {
        "id": 4,
        "slug": "seed-feature-delta",
        "status": "refined",
        "priority": "medium",
        "type": "feature",
        "title": "Implement rate limiting for export endpoints",
        "lifecycle_slug": "seed-feature-delta",
    },
    # 005 — terminal blocker target for 008: resolves silently, so the item it
    # blocks still lands ready while the blocker stays listed.
    {
        "id": 5,
        "slug": "seed-feature-epsilon",
        "status": "complete",
        "priority": "low",
        "type": "chore",
        "title": "Deprecate legacy webhook handler",
    },
    # 006 — the epic. schema_version must render as the string "1": the epic
    # map raises SchemaVersionError on anything else, and this record is the
    # one that flows through that path.
    {
        "id": 6,
        "slug": "seed-epic-command-station",
        "status": "backlog",
        "priority": "high",
        "type": "epic",
        "title": "Command-station dashboard",
        "body": _EPIC_BODY,
    },
    # 007 — epic child plus internal non-terminal blocker, so it is both a
    # child in the epic map and ineligible with a blocker cause.
    {
        "id": 7,
        "slug": "seed-epic-child-blocked",
        "status": "backlog",
        "priority": "medium",
        "type": "feature",
        "title": "Board columns for the command station",
        "parent": "006",
        "blocked_by": ["002"],
    },
    # 008 — epic child plus internal terminal blocker plus the rich body.
    {
        "id": 8,
        "slug": "seed-epic-child-rich",
        "status": "refined",
        "priority": "high",
        "type": "feature",
        "title": "Ticket reader for the command station",
        "parent": "006",
        "blocked_by": ["005"],
        "body": _RICH_BODY,
    },
    # 009 — parent names a feature, not an epic, so the epic map drops the
    # relationship silently; the blocker is an external reference.
    {
        "id": 9,
        "slug": "seed-orphan-child-external",
        "status": "backlog",
        "priority": "low",
        "type": "chore",
        "title": "Track the upstream sandbox regression",
        "parent": "001",
        "blocked_by": ["anthropics/claude-code#34243"],
    },
    # 010 — a well-formed UUID matching no item in the corpus: not_found, which
    # is a different outcome from an external reference and renders differently.
    {
        "id": 10,
        "slug": "seed-blocked-missing-uuid",
        "status": "backlog",
        "priority": "medium",
        "type": "bug",
        "title": "Poller drops the first event after a restart",
        "blocked_by": ["6ba7b810-9dad-11d1-80b4-00c04fd430c8"],
    },
    # 011 — deferral vocabulary one: a deferred *status*, which is also the
    # only fixture ineligible for a status reason rather than a blocker.
    {
        "id": 11,
        "slug": "seed-deferred-status",
        "status": "deferred",
        "priority": "low",
        "type": "feature",
        "title": "Multi-repo fleet view",
    },
    # 012 — deferral vocabulary two: a deferred *tag* at an eligible status, so
    # the item is legitimately ready and deferred at the same time.
    {
        "id": 12,
        "slug": "seed-deferred-tag",
        "status": "backlog",
        "priority": "medium",
        "type": "chore",
        "title": "Prune the stale worktree registry",
        "extra_tags": ["deferred"],
    },
    # 013 — the deliberate dead artifact link. Both paths name a lifecycle slug
    # the seeder never creates, so every reader that follows them dangles. Do
    # NOT "fix" this by pointing it at a directory that exists: dead artifact
    # links are the defect the command-station epic exists to surface, and this
    # is the corpus's only coverage of that state.
    {
        "id": 13,
        "slug": "seed-dangling-artifact",
        "status": "backlog",
        "priority": "low",
        "type": "feature",
        "title": "Export the session timeline as CSV",
        "lifecycle_slug": "seed-feature-missing",
        "spec": "cortex/lifecycle/seed-feature-missing/spec.md",
    },
    # 014 — the archived fixture, written under cortex/backlog/archive/ so the
    # snapshot has a non-empty archive id set and a non-zero archived count.
    {
        "id": 14,
        "slug": "seed-archived-item",
        "status": "complete",
        "priority": "low",
        "type": "chore",
        "title": "Retire the v1 metrics exporter",
        "archived": True,
    },
    # 015 — a CLOSED epic. Terminal, so it is filtered out of the active items,
    # which is exactly why it belongs here: the epic map is built by scanning
    # for `type: epic`, and scanning the active slice made this one invisible
    # as an epic at all. Its live child 016 then rendered as Standalone. Do NOT
    # "fix" this by reopening it — an epic closing before its children are all
    # done is the normal end state (the parent-closing cascade fires on the
    # last child, and #438 documents epic 9 absorbing a child 39 days later),
    # and this pair is the corpus's only coverage of it.
    {
        "id": 15,
        "slug": "seed-epic-closed",
        "status": "complete",
        "priority": "medium",
        "type": "epic",
        "title": "Ship the v1 telemetry pipeline",
    },
    # 016 — the late-arriving child: filed against 015 after it closed, and
    # still active. It must render inside 015's group, never as Standalone.
    {
        "id": 16,
        "slug": "seed-late-child-of-closed-epic",
        "status": "backlog",
        "priority": "high",
        "type": "bug",
        "title": "Telemetry exporter drops the final batch on shutdown",
        "parent": "015",
    },
]

# Deterministic UUIDs for seed backlog items so reruns don't churn frontmatter.
# Distinct from the dispatch-ID range used for seed-feature-* lifecycle dirs.
# One entry per _BACKLOG_ITEMS record, keyed by slug — a record without one
# fails loudly at write time rather than emitting a colliding id.
_BACKLOG_UUIDS = {
    "seed-feature-alpha":         "5eed0001-0000-4000-8000-000000000001",
    "seed-feature-beta":          "5eed0002-0000-4000-8000-000000000002",
    "seed-feature-gamma":         "5eed0003-0000-4000-8000-000000000003",
    "seed-feature-delta":         "5eed0004-0000-4000-8000-000000000004",
    "seed-feature-epsilon":       "5eed0005-0000-4000-8000-000000000005",
    "seed-epic-command-station":  "5eed0006-0000-4000-8000-000000000006",
    "seed-epic-child-blocked":    "5eed0007-0000-4000-8000-000000000007",
    "seed-epic-child-rich":       "5eed0008-0000-4000-8000-000000000008",
    "seed-orphan-child-external": "5eed0009-0000-4000-8000-000000000009",
    "seed-blocked-missing-uuid":  "5eed0010-0000-4000-8000-000000000010",
    "seed-deferred-status":       "5eed0011-0000-4000-8000-000000000011",
    "seed-deferred-tag":          "5eed0012-0000-4000-8000-000000000012",
    "seed-dangling-artifact":     "5eed0013-0000-4000-8000-000000000013",
    "seed-archived-item":         "5eed0014-0000-4000-8000-000000000014",
    "seed-epic-closed":           "5eed0015-0000-4000-8000-000000000015",
    "seed-late-child-of-closed-epic": "5eed0016-0000-4000-8000-000000000016",
}


def _quoted(value: str) -> str:
    """Return ``value`` as a YAML double-quoted scalar."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _inline_list(values: list[str]) -> str:
    """Render a YAML array in the inline ``[a, b]`` form.

    The backlog schema requires this form and the index reader's parser
    understands no other, so the multiline ``- item`` form would silently
    produce an empty list rather than an error.
    """
    return "[" + ", ".join(values) + "]"


def _backlog_item_path(backlog_dir: Path, record: dict) -> Path:
    """Return the file path for one fixture record — archived or active.

    ``write_backlog_items`` and ``clean_all`` both route through this helper,
    so the archive fixture can never be written to one path and looked for at
    another. The archive directory is created under the isolated fixture root
    only; the seeder never ``mkdir``s into a project tree.
    """
    directory = backlog_dir / "archive" if record.get("archived") else backlog_dir
    return directory / f"{record['id']:03d}-{record['slug']}.md"


def _render_backlog_item(record: dict, today: str) -> str:
    """Render one fixture record as backlog markdown.

    Fields are emitted in the canonical order from
    skills/backlog/references/schema.md, and an optional field a record does
    not declare is omitted entirely rather than written as an empty scalar —
    an empty scalar reads back as a populated-but-blank field, which is a
    different fact from "absent".

    ``parent``, ``spec``, and ``lifecycle_slug`` are quoted because they sit on
    the string-intended-key allowlist: unquoted, a numeric-looking value reads
    back as an integer. ``schema_version`` is emitted as the exact string
    ``"1"`` because the epic map raises on anything else.
    """
    lines = [
        "---",
        'schema_version: "1"',
        f"uuid: {_BACKLOG_UUIDS[record['slug']]}",
        f"title: {_quoted(SEED_TITLE_PREFIX + record['title'])}",
        f"status: {record['status']}",
        f"priority: {record['priority']}",
        f"type: {record['type']}",
        f"tags: {_inline_list([SEED_TAG, *record.get('extra_tags', [])])}",
    ]
    if "areas" in record:
        lines.append(f"areas: {_inline_list(record['areas'])}")
    lines.append(f"created: {today}")
    lines.append(f"updated: {today}")
    if "lifecycle_slug" in record:
        lines.append(f"lifecycle_slug: {_quoted(record['lifecycle_slug'])}")
    if "blocked_by" in record:
        lines.append(f"blocked-by: {_inline_list(record['blocked_by'])}")
    if "parent" in record:
        lines.append(f"parent: {_quoted(record['parent'])}")
    if "spec" in record:
        lines.append(f"spec: {_quoted(record['spec'])}")
    lines.append("---")

    return "\n".join(lines) + "\n\n" + record.get("body", _DEFAULT_BODY)


def write_backlog_items(repo_root: Path) -> list[Path]:
    """Write one backlog markdown file per ``_BACKLOG_ITEMS`` record.

    Active fixtures land in ``cortex/backlog/``; the archived fixture lands in
    ``cortex/backlog/archive/``. ``clean_all`` derives its backlog removals
    from the same table through the same ``_backlog_item_path`` helper, so
    renumbering or re-siting a fixture cannot desynchronize the pair.

    Args:
        repo_root: Absolute path to the repository root.

    Returns:
        List of Paths that were written, archived fixture included.
    """
    backlog_dir = repo_root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    written: list[Path] = []
    for record in _BACKLOG_ITEMS:
        path = _backlog_item_path(backlog_dir, record)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render_backlog_item(record, today), encoding="utf-8")
        written.append(path)
        rel = path.relative_to(backlog_dir).as_posix()
        print(f"  wrote cortex/backlog/{rel}")

    return written


# ---------------------------------------------------------------------------
# Seed / clean entry points
# ---------------------------------------------------------------------------


def write_latest_overnight_pointer(session_dir: Path) -> bool:
    """Point ``sessions/latest-overnight`` at the seeded session directory.

    Without this the seeded dashboard renders as an idle, sessionless page.
    The seeder writes a copy of the state and event files at
    ``cortex/lifecycle/`` and the real session files under
    ``sessions/{session_id}/``, but the poller's ``_resolve_session_path``
    reads neither: absent the ``~/.local/share/overnight-sessions`` pointer it
    falls back to ``sessions/latest-overnight/`` and nothing else. So every
    panel downstream of ``state.overnight`` — session, features, fleet,
    timeline, rounds, escalations, activity — showed its empty state, and
    ``just dashboard-demo`` demonstrated an empty dashboard.

    Mirrors ``overnight.runner._point_latest_overnight``: a relative symlink so
    the fixture root stays movable, best-effort so a filesystem without symlink
    support degrades to the old behaviour rather than failing the seed, and a
    real directory at that path is left alone. Returns True when the link is in
    place, so the caller lists it among the files written.
    """
    link = session_dir.parent / "latest-overnight"
    try:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            print(f"  WARNING: {link} is a real directory — leaving it alone.")
            return False
        link.symlink_to(session_dir.name, target_is_directory=True)
        return True
    except OSError as exc:
        print(f"  WARNING: could not point latest-overnight at {session_dir.name} ({exc}).")
        return False


def write_all(repo_root: Path, session_id: str) -> None:
    """Write all fixture files: overnight state, events, per-feature files,
    pipeline fixtures, metrics, and backlog items.

    Args:
        repo_root: Absolute path to the repository root.
        session_id: Session ID string for the seed session.
    """
    session_dir = repo_root / "cortex" / "lifecycle" / "sessions" / session_id
    written_paths: list[Path] = []

    write_overnight_state(repo_root, session_dir, session_id)
    written_paths.append(session_dir / "overnight-state.json")
    written_paths.append(repo_root / "cortex" / "lifecycle" / "overnight-state.json")

    write_overnight_events(repo_root, session_dir, session_id)
    written_paths.append(session_dir / "overnight-events.log")
    written_paths.append(repo_root / "cortex" / "lifecycle" / "overnight-events.log")

    if write_latest_overnight_pointer(session_dir):
        written_paths.append(session_dir.parent / "latest-overnight")

    for slug, status, *_ in _FEATURES:
        write_feature_files(repo_root, slug, status)
        feature_dir = repo_root / "cortex" / "lifecycle" / slug
        written_paths.append(feature_dir / "agent-activity.jsonl")
        written_paths.append(feature_dir / "events.log")
        written_paths.append(feature_dir / "plan.md")

        # research.md / spec.md for the feature a backlog fixture links to.
        for name in write_feature_artifacts(repo_root, slug):
            written_paths.append(feature_dir / name)

        # Extended fixtures for the new dashboard panels.
        # write_enriched_events_log replaces the basic events.log written above.
        write_enriched_events_log(repo_root, slug, status)

        if write_escalations(repo_root, slug):
            written_paths.append(feature_dir / "escalations.jsonl")

        report_count = write_exit_reports(repo_root, slug, status)
        for i in range(1, report_count + 1):
            written_paths.append(feature_dir / "exit-reports" / f"{i}.json")

        if write_learnings_progress(repo_root, slug, status):
            written_paths.append(feature_dir / "learnings" / "progress.txt")

    write_pipeline_fixtures(repo_root)
    written_paths.append(repo_root / "cortex" / "lifecycle" / "pipeline-state.json")
    written_paths.append(repo_root / "cortex" / "lifecycle" / "pipeline-events.log")

    write_metrics(repo_root)
    written_paths.append(repo_root / "cortex" / "lifecycle" / "metrics.json")

    backlog_paths = write_backlog_items(repo_root)
    written_paths.extend(backlog_paths)

    print("\nFiles written:")
    for path in written_paths:
        print(f"  {path.relative_to(repo_root)}")


def run_seed(root: Path) -> None:
    """Write all fixture files under ``root`` and print the viewing command.

    Args:
        root: Absolute path to the fixture root to seed.
    """
    print(f"Seeding dashboard fixtures into {root} (session: {SESSION_ID}) …")
    write_seed_marker(root)
    write_all(root, SESSION_ID)
    print("Done.")
    print("\nView the seeded fixtures with:")
    print(f"  cortex dashboard --root {root}")


def _seed_content_signals() -> list[str]:
    """Return the fixture names that identify a file as this seeder's output.

    Derived from the same tables the writers render, so renaming a fixture can
    never leave the cleaner matching a name nothing writes any more.
    """
    return [slug for slug, *_ in _FEATURES] + list(PIPELINE_FEATURES)


def _unlink_if_seed_content(path: Path, rel: str, removed: list[str]) -> None:
    """Unlink ``path`` only when its content names one of the seed fixtures.

    ``--clean`` runs against whatever root it is handed, and a real repository
    keeps live ``pipeline-state.json`` / ``pipeline-events.log`` /
    ``metrics.json`` files at exactly these paths — some of them git-tracked.
    The pre-containment cleaner unlinked all three unconditionally, so a
    ``--clean`` in a never-seeded repository deleted real, tracked state. Every
    removal is now gated on the file naming a fixture the writers produce.
    """
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  WARNING: could not read {rel} ({exc}), skipping.")
        return
    if any(signal in text for signal in _seed_content_signals()):
        path.unlink()
        removed.append(rel)
    else:
        print(f"  WARNING: {rel} names no seed fixture — not a seed file, skipping.")


def _prune_empty_dirs(candidates: list[Path], root: Path, removed: list[str]) -> None:
    """Remove each candidate directory under ``root``, deepest first, when empty.

    The writers create directories as well as files — ``exit-reports/``,
    ``learnings/``, one directory per feature, the session directory, and the
    ``.claude/`` marker directory — and ``write_all``'s hand-assembled
    ``written_paths`` records none of them. Without this pass a seed/clean cycle
    leaves the tree littered with empty directories rather than returning it to
    its prior state. A directory goes only when it is empty once its own files
    are gone, so anything the seeder did not write keeps its parent alive.
    """
    for directory in sorted(set(candidates), key=lambda p: len(p.parts), reverse=True):
        if directory == root or root not in directory.parents:
            continue
        if not directory.is_dir():
            continue
        # rmdir raises OSError when the directory still holds anything.
        with suppress(OSError):
            directory.rmdir()
            removed.append(f"{directory.relative_to(root)}/")


def clean_all(root: Path) -> None:
    """Remove every file and directory a previous seed run wrote under ``root``.

    Scoped entirely to ``root`` — the resolved fixture root — and derived from
    the same tables the writers render, so the writer/cleaner pair cannot
    desynchronize when the fixtures are renamed or renumbered.

    Removal order:
    1. cortex/lifecycle/overnight-state.json — only if session_id names a seed session
    2. cortex/lifecycle/overnight-events.log — only if its first line names one
    3. cortex/lifecycle/sessions/{SEED_PREFIX}-*/ directories (shutil.rmtree)
    4. One cortex/lifecycle/{slug}/ directory per ``_FEATURES`` entry (shutil.rmtree)
    5. cortex/lifecycle/{pipeline-state.json,pipeline-events.log,metrics.json} —
       only when their content names a seed fixture
    6. One backlog file per ``_BACKLOG_ITEMS`` record, active or archived,
       resolved through the same ``_backlog_item_path`` helper the writer uses
    7. The ``.claude/`` seed marker file
    8. Every directory the writers created, pruned bottom-up when empty

    Args:
        root: Absolute path to the fixture root to clean.
    """
    removed: list[str] = []
    prune: list[Path] = []
    lifecycle_dir = root / "cortex" / "lifecycle"
    backlog_dir = root / "cortex" / "backlog"

    # 1. cortex/lifecycle/overnight-state.json — guard: session_id must name a seed session
    overnight_state = lifecycle_dir / "overnight-state.json"
    if overnight_state.exists():
        try:
            data = json.loads(overnight_state.read_text(encoding="utf-8"))
            session_id = data.get("session_id", "")
            if SEED_PREFIX in session_id:
                overnight_state.unlink()
                removed.append("cortex/lifecycle/overnight-state.json")
            else:
                print(
                    f"  WARNING: cortex/lifecycle/overnight-state.json has session_id={session_id!r}"
                    " — not a seed file, skipping."
                )
        except Exception as exc:
            print(f"  WARNING: could not parse cortex/lifecycle/overnight-state.json ({exc}), skipping.")

    # 2. cortex/lifecycle/overnight-events.log — guard: first line must name a seed session
    overnight_events = lifecycle_dir / "overnight-events.log"
    if overnight_events.exists():
        try:
            first_line = overnight_events.read_text(encoding="utf-8").splitlines()[0]
            if SEED_PREFIX in first_line:
                overnight_events.unlink()
                removed.append("cortex/lifecycle/overnight-events.log")
            else:
                print(
                    "  WARNING: cortex/lifecycle/overnight-events.log first line does not name"
                    f" a seed session ({SEED_PREFIX}) — not a seed file, skipping."
                )
        except Exception as exc:
            print(f"  WARNING: could not read cortex/lifecycle/overnight-events.log ({exc}), skipping.")

    # 3. Session directories — the prefix the seeder builds SESSION_ID from
    sessions_dir = lifecycle_dir / "sessions"
    # The latest-overnight pointer goes first, and only while it still resolves
    # to a seed session: in a real repository the same path is the runner's own
    # link to live state. ``is_symlink`` is the guard that keeps a real
    # directory at that path intact, and readlink is compared rather than
    # followed so a dangling seed link is still cleaned up.
    pointer = sessions_dir / "latest-overnight"
    if pointer.is_symlink():
        if os.readlink(pointer).startswith(SEED_PREFIX):
            pointer.unlink()
            removed.append("cortex/lifecycle/sessions/latest-overnight")
        else:
            print(
                "  WARNING: cortex/lifecycle/sessions/latest-overnight points outside"
                f" a seed session ({SEED_PREFIX}) — not a seed link, skipping."
            )
    for session_dir in sorted(sessions_dir.glob(f"{SEED_PREFIX}-*")):
        if session_dir.is_dir():
            shutil.rmtree(session_dir)
            removed.append(f"cortex/lifecycle/sessions/{session_dir.name}/")
    prune.append(sessions_dir)

    # 4. One feature directory per _FEATURES entry — the same table write_all
    #    iterates, rather than a glob that would also match a real feature.
    for slug, *_ in _FEATURES:
        feature_dir = lifecycle_dir / slug
        prune.extend([feature_dir / "exit-reports", feature_dir / "learnings", feature_dir])
        if feature_dir.is_dir():
            shutil.rmtree(feature_dir)
            removed.append(f"cortex/lifecycle/{slug}/")

    # 5. Pipeline and metrics fixtures — content-gated (see _unlink_if_seed_content)
    for name in ("pipeline-state.json", "pipeline-events.log", "metrics.json"):
        _unlink_if_seed_content(lifecycle_dir / name, f"cortex/lifecycle/{name}", removed)

    # 6. One backlog file per _BACKLOG_ITEMS record, sited exactly where
    #    write_backlog_items sited it — archive/ included.
    for record in _BACKLOG_ITEMS:
        path = _backlog_item_path(backlog_dir, record)
        with suppress(FileNotFoundError):
            path.unlink()
            removed.append(f"cortex/backlog/{path.relative_to(backlog_dir).as_posix()}")

    # 7. The .claude/ marker file write_seed_marker created
    marker_dir = root / ".claude"
    with suppress(FileNotFoundError):
        (marker_dir / SEED_MARKER_NAME).unlink()
        removed.append(f".claude/{SEED_MARKER_NAME}")

    # 8. Prune the directories the writers created, bottom-up, when empty
    prune.extend([
        marker_dir,
        backlog_dir / "archive",
        backlog_dir,
        lifecycle_dir,
        root / "cortex",
    ])
    _prune_empty_dirs(prune, root, removed)

    # Summary
    if removed:
        print("\nRemoved:")
        for item in removed:
            print(f"  {item}")
    else:
        print("  Nothing to remove.")


def run_clean(root: Path) -> None:
    """Remove all files created by a previous seed run under ``root``.

    Args:
        root: Absolute path to the fixture root to clean.
    """
    print(f"Cleaning seed fixture files under {root} …")
    clean_all(root)
    print("Done.")


# ---------------------------------------------------------------------------
# Legacy fixture sweep (one-time migration off the pre-containment seeder)
# ---------------------------------------------------------------------------

#: Filenames the pre-containment seeder wrote into a project repository's own
#: ``cortex/backlog/``. Anchored to exactly the five fixture names it produced:
#: a broader ``^\d+-seed-`` would also match a real ticket titled something like
#: "Seed feature flags system", whose file the operator would then lose.
_LEGACY_FIXTURE_RE = re.compile(
    r"^99\d-seed-feature-(alpha|beta|gamma|delta|epsilon)\.md$"
)


def _is_git_tracked(root: Path, path: Path) -> bool:
    """Return True when git reports ``path`` as tracked inside ``root``."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", str(path)],
            capture_output=True,
            check=False,
        )
    except OSError:
        # No git available (or no repository) — treat the file as untracked.
        return False
    return result.returncode == 0


def sweep_legacy_backlog(project_root: Path) -> list[str]:
    """Remove pre-containment seed fixture files from a project repository.

    A one-time migration for operators who ran the seeder before it was
    contained to an isolated fixture root: those runs left fixture files in the
    real ``cortex/backlog/``, and with the ID reservation deleted the allocator
    now sees them and would push a real sequence past them permanently.

    Git-tracked matches are reported and left in place — untracking a committed
    file is a reviewable commit, not something a fixture script does silently.

    Args:
        project_root: Absolute path to the project repository to sweep.

    Returns:
        Repo-relative paths of the files that were removed.
    """
    backlog_dir = project_root / "cortex" / "backlog"
    removed: list[str] = []
    for path in sorted(backlog_dir.glob("*.md")):
        if not _LEGACY_FIXTURE_RE.match(path.name):
            continue
        if _is_git_tracked(project_root, path):
            print(
                f"  WARNING: cortex/backlog/{path.name} is git-tracked — skipping."
                " Remove it with `git rm` so the deletion is reviewed."
            )
            continue
        with suppress(FileNotFoundError):
            path.unlink()
            removed.append(f"cortex/backlog/{path.name}")
    return removed


def run_sweep_legacy(project_root: Path) -> None:
    """Sweep pre-containment fixture files from ``project_root`` and report.

    Args:
        project_root: Absolute path to the project repository to sweep.
    """
    print(f"Sweeping pre-containment seed fixtures from {project_root} …")
    removed = sweep_legacy_backlog(project_root)
    if removed:
        print("\nRemoved:")
        for item in removed:
            print(f"  {item}")
    else:
        print("  Nothing to remove.")
    print("Done.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments, resolve the fixture root, and dispatch."""
    parser = argparse.ArgumentParser(
        prog="python3 -m cortex_command.dashboard.seed",
        description=(
            "Write realistic fixture files for the monitoring dashboard, "
            "enabling visual testing without running a real overnight workflow. "
            "Fixtures go to an isolated per-user fixture root, not your repository."
        ),
    )
    parser.add_argument(
        "--root",
        metavar="PATH",
        help=(
            "Seed (or clean) PATH instead of the default per-user fixture root "
            "${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/dashboard-seed."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all files previously written by the seed script.",
    )
    parser.add_argument(
        "--sweep-legacy",
        metavar="PATH",
        nargs="?",
        const="",
        help=(
            "One-time migration: remove the backlog fixture files an older, "
            "pre-containment seed run left in a project repository at PATH "
            "(default: the resolved cortex project root). Git-tracked matches "
            "are reported and left alone. Combine with --clean, or run alone."
        ),
    )
    parser.add_argument(
        "--print-root",
        action="store_true",
        help="Print the resolved fixture root and exit without writing anything.",
    )
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).expanduser().absolute()
    else:
        root = _resolve_fixture_root()

    if args.print_root:
        print(root)
        return

    sweeping = args.sweep_legacy is not None
    if sweeping:
        if args.sweep_legacy:
            sweep_root = Path(args.sweep_legacy).expanduser().absolute()
        else:
            sweep_root = _common._resolve_user_project_root()
        run_sweep_legacy(sweep_root)

    if args.clean:
        run_clean(root)
    elif not sweeping:
        run_seed(root)


if __name__ == "__main__":
    main()
