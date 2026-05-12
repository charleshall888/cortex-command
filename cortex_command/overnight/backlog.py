"""Backlog item parser and scoring for overnight orchestration.

Scans the backlog directory for numbered markdown files (NNN-*.md),
extracts YAML frontmatter between ``---`` delimiters, and returns
structured BacklogItem instances.  Includes a weighted scoring algorithm
for prioritising eligible items during overnight session planning.

Frontmatter is parsed manually without PyYAML — the format is simple
key-value pairs with optional inline arrays like ``[tag1, tag2]``.
"""

from __future__ import annotations

import collections
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Named tuple for ineligible items — supports both attribute access (.item, .reason)
# and tuple unpacking/indexing for backward compatibility.
IneligibleItem = collections.namedtuple('IneligibleItem', ['item', 'reason'])

from cortex_command.backlog import is_item_ready
from cortex_command.common import TERMINAL_STATUSES, normalize_status, slugify


# ---------------------------------------------------------------------------
# Valid enum values for validation
# ---------------------------------------------------------------------------

STATUSES = (
    "open", "in-progress", "blocked", "resolved", "wontfix", "done",
    "backlog", "ready", "refined", "in_progress", "implementing", "review", "complete", "abandoned",
)
ELIGIBLE_STATUSES = ("backlog", "ready", "in_progress", "implementing", "refined")
PRIORITIES = ("critical", "high", "medium", "low")
TYPES = ("feature", "bug", "chore", "spike", "idea", "epic")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BacklogItem:
    """A single backlog item parsed from a numbered markdown file.

    Fields:
        id: Numeric ID extracted from the filename prefix (e.g. 33).
        title: Human-readable title.
        status: Workflow status (canonical: backlog, in_progress, implementing,
            review, complete, abandoned).
        priority: Priority level (critical, high, medium, low).
        type: Item type (feature, bug, chore, spike, idea, epic).
        tags: List of string tags.
        areas: List of area labels (e.g. ["overnight", "lifecycle"]).
        created: Date string from frontmatter (e.g. "2026-02-21").
        updated: Date string from frontmatter.
        blocks: List of backlog item IDs (strings — UUIDs or stringified integers).
        blocked_by: List of backlog item IDs (strings — UUIDs or stringified integers).
        parent: Optional parent backlog item ID (string — UUID or stringified integer).
        research: Optional path to research artifact.
        spec: Optional path to spec artifact.
        plan: Optional path to implementation plan artifact (lifecycle/<slug>/plan.md).
            Required for overnight execution.
        uuid: Optional UUID v4 identifier (canonical cross-reference key).
        lifecycle_slug: Optional kebab-case slug linking to lifecycle/{slug}/.
        session_id: Optional session ID of the session currently working on this item.
        lifecycle_phase: Optional current lifecycle phase (research, specify, plan,
            implement, implement-rework, review, complete, escalated).
        schema_version: Optional schema version string (e.g. "1").
    """

    id: int = 0
    title: str = ""
    status: str = "open"
    priority: str = "medium"
    type: str = "feature"
    tags: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    created: str = ""
    updated: str = ""
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    parent: Optional[str] = None
    research: Optional[str] = None
    spec: Optional[str] = None
    discovery_source: Optional[str] = None
    plan: Optional[str] = None
    uuid: Optional[str] = None
    lifecycle_slug: Optional[str] = None
    session_id: Optional[str] = None
    lifecycle_phase: Optional[str] = None
    schema_version: Optional[str] = None
    repo: Optional[str] = None

    def resolve_slug(self) -> str:
        """Derive lifecycle slug with fallback chain.

        Priority: lifecycle_slug > slug extracted from spec/research path > slugify(title).
        The spec/research paths in frontmatter point to the actual lifecycle directory,
        so extracting the slug from them handles cases where the directory name diverges
        from slugify(title) (e.g., underscores stripped vs hyphenated).
        """
        if self.lifecycle_slug:
            return self.lifecycle_slug
        for artifact_path in (self.spec, self.research):
            if artifact_path:
                parent = Path(artifact_path).parent.name
                if parent and parent != ".":
                    return parent
        return slugify(self.title)


@dataclass
class Batch:
    """A grouped batch of backlog items for overnight execution.

    Fields:
        items: Backlog items assigned to this batch.
        batch_context: Summary of the batch's knowledge domain, e.g.
            "Features in auth, ui subsystems".
        batch_id: 1-based sequential batch identifier.
    """

    items: list[BacklogItem] = field(default_factory=list)
    batch_context: str = ""
    batch_id: int = 0

    @property
    def batch_number(self) -> int:
        """Alias for batch_id — the 1-based sequential batch identifier."""
        return self.batch_id


@dataclass
class SelectionResult:
    """Result of the full backlog selection pipeline.

    Fields:
        batches: Grouped batches of eligible items for overnight execution.
        ineligible: Items that failed readiness checks, each paired with a reason.
        summary: Human-readable summary string for the session plan.
        intra_session_deps: Mapping from dependent item slug to list of blocker
            slugs that must complete before it runs.
    """

    batches: list[Batch] = field(default_factory=list)
    ineligible: list[tuple[BacklogItem, str]] = field(default_factory=list)
    summary: str = ""
    intra_session_deps: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ineligible_items(self) -> list[tuple[BacklogItem, str]]:
        """Alias for ineligible — items that failed readiness checks with reasons."""
        return self.ineligible


@dataclass
class ReadinessResult:
    """Result of filtering backlog items for overnight execution readiness.

    Fields:
        eligible: Items that pass all readiness checks.
        ineligible: Items that failed a check, each paired with a reason string.
        intra_session_blocked: Items blocked only by other session-eligible items,
            each paired with the list of blocker slugs that must run first.
    """

    eligible: list[BacklogItem] = field(default_factory=list)
    ineligible: list[tuple[BacklogItem, str]] = field(default_factory=list)
    intra_session_blocked: list[tuple[BacklogItem, list[str]]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter parsing helpers
# ---------------------------------------------------------------------------

# Pattern to match the numeric prefix in filenames like 033-backlog-readiness-gate.md or 1004-feature.md
_FILENAME_ID_RE = re.compile(r"^(\d+)-")

# Pattern to extract frontmatter block between --- delimiters
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def _parse_inline_str_list(raw: str) -> list[str]:
    """Parse an inline YAML list like ``[tag1, tag2, tag3]``.

    Returns an empty list for ``[]`` or missing brackets.
    """
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    # Bare scalar — treat as single-element list
    if raw:
        return [raw]
    return []


def _parse_inline_id_list(val: str) -> list[str]:
    """Parse an inline YAML list of IDs (integers or UUID strings).

    Accepts formats like ``[32, 35]``, ``[550e8400-...]``, or mixed.
    Integer values are returned as their string representation (e.g. ``"32"``).

    Returns an empty list for ``[]`` or missing brackets.
    """
    return _parse_inline_str_list(val)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract key-value pairs from frontmatter text (between --- lines).

    Returns a dict mapping lowercase keys to their raw string values.
    Only handles simple ``key: value`` lines — no nested YAML.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}

    block = match.group(1)
    pairs: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Split on first colon only
        colon_idx = line.find(":")
        if colon_idx < 0:
            continue
        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()
        pairs[key] = value
    return pairs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

DEFAULT_BACKLOG_DIR = Path("cortex/backlog")


def parse_backlog_dir(
    backlog_dir: Path = DEFAULT_BACKLOG_DIR,
) -> list[BacklogItem]:
    """Scan a backlog directory and return parsed BacklogItem instances.

    Looks for files matching ``[0-9]*-*.md`` in *backlog_dir*.
    Excludes any files inside an ``archive/`` subdirectory and the
    ``index.md`` file.

    Args:
        backlog_dir: Path to the backlog directory. Defaults to
            ``backlog/`` relative to the current working directory.

    Returns:
        List of BacklogItem instances sorted by ID (ascending).
    """
    backlog_dir = Path(backlog_dir)
    if not backlog_dir.is_dir():
        return []

    items: list[BacklogItem] = []

    for path in sorted(backlog_dir.glob("[0-9]*-*.md")):
        # Exclude archive/ subdirectory items
        if "archive" in path.parts:
            continue

        # Exclude index.md (shouldn't match the glob, but be safe)
        if path.name == "index.md":
            continue

        # Extract numeric ID from filename
        id_match = _FILENAME_ID_RE.match(path.name)
        if not id_match:
            continue
        item_id = int(id_match.group(1))

        # Read file and parse frontmatter
        text = path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if not fm:
            continue

        # Normalize status from legacy values to canonical vocabulary
        raw_status = fm.get("status", "open")
        status = normalize_status(raw_status)

        # Parse parent — accept both integer and UUID string
        raw_parent = fm.get("parent", "").strip()
        parent = raw_parent if raw_parent else None

        # Build the BacklogItem
        item = BacklogItem(
            id=item_id,
            title=fm.get("title", ""),
            status=status,
            priority=fm.get("priority", "medium"),
            type=fm.get("type", "feature"),
            tags=_parse_inline_str_list(fm.get("tags", "[]")),
            areas=_parse_inline_str_list(fm.get("areas", "[]")),
            created=fm.get("created", ""),
            updated=fm.get("updated", ""),
            blocks=_parse_inline_id_list(fm.get("blocks", "[]")),
            blocked_by=_parse_inline_id_list(fm.get("blocked-by", "[]")),
            parent=parent,
            research=fm.get("research") or None,
            spec=fm.get("spec") or None,
            discovery_source=fm.get("discovery_source") or None,
            plan=fm.get("plan") or None,
            uuid=fm.get("uuid") or None,
            lifecycle_slug=fm.get("lifecycle_slug") or None,
            session_id=fm.get("session_id") or None,
            lifecycle_phase=fm.get("lifecycle_phase") or None,
            schema_version=fm.get("schema_version") or None,
            repo=fm.get("repo") or None,
        )
        items.append(item)

    # Sort by ID (should already be sorted from glob, but be explicit)
    items.sort(key=lambda item: item.id)
    return items


def load_from_index(backlog_dir: Path = DEFAULT_BACKLOG_DIR) -> list[BacklogItem]:
    """Load BacklogItem instances from backlog/index.json.

    Raises:
        FileNotFoundError: If index.json does not exist.
        json.JSONDecodeError: If index.json is malformed.
    """
    index_path = backlog_dir / "index.json"
    entries: list[dict] = json.loads(index_path.read_text(encoding="utf-8"))
    items: list[BacklogItem] = []
    for entry in entries:
        items.append(BacklogItem(
            id=int(entry["id"]),
            title=entry["title"],
            status=entry["status"],
            priority=entry["priority"],
            type=entry["type"],
            tags=entry.get("tags") or [],
            areas=entry.get("areas") or [],
            created=entry.get("created", ""),
            updated=entry.get("updated", ""),
            blocks=entry.get("blocks") or [],
            blocked_by=[
                s.strip("'\"") for s in (entry.get("blocked_by") or [])
            ],
            parent=entry.get("parent"),
            research=entry.get("research"),
            spec=entry.get("spec"),
            discovery_source=entry.get("discovery_source"),
            plan=entry.get("plan"),
            uuid=entry.get("uuid"),
            lifecycle_slug=entry.get("lifecycle_slug"),
            session_id=entry.get("session_id"),
            lifecycle_phase=entry.get("lifecycle_phase"),
            schema_version=entry.get("schema_version"),
            repo=entry.get("repo"),
        ))
    return items


def _is_pipeline_branch_merged(slug: str, project_root: Path) -> bool:
    """Return True if all local pipeline/{slug}* branches are merged into main.

    Uses two git subprocesses:
    1. ``git branch --list pipeline/{slug}*`` — enumerate matching branches.
    2. ``git log --oneline main..{branch}`` per branch — empty output means merged.

    Returns False (fail open) when:
    - No matching branches exist (item may be freshly refined, not yet started).
    - Any branch has non-empty ``git log`` output (unmerged commits exist).
    - ``slug`` is empty.
    - Any subprocess raises ``OSError`` or ``TimeoutExpired``.
    - Any subprocess returns a non-zero exit code.
    """
    if not slug:
        return False

    try:
        list_result = subprocess.run(
            ["git", "branch", "--list", f"pipeline/{slug}*"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    if list_result.returncode != 0:
        return False

    branches = [
        line.strip().lstrip("* ")
        for line in list_result.stdout.splitlines()
        if line.strip()
    ]
    if not branches:
        return False

    for branch in branches:
        try:
            log_result = subprocess.run(
                ["git", "log", "--oneline", f"main..{branch}"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=project_root,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        if log_result.returncode != 0:
            return False

        if log_result.stdout.strip():
            return False

    return True


def filter_ready(
    items: list[BacklogItem],
    all_items: list[BacklogItem] | None = None,
    project_root: Path | None = None,
) -> ReadinessResult:
    """Partition backlog items into eligible and ineligible for overnight execution.

    Uses ``item.lifecycle_slug`` (falling back to ``slugify(item.title)``) to
    derive artifact paths under ``lifecycle/{slug}/``.

    Readiness gates: (1) status in ``ELIGIBLE_STATUSES`` and (2) blockers
    delegate to :func:`cortex_command.backlog.is_item_ready`. (3) epics are
    excluded. (4) ``research.md`` and (5) ``spec.md`` must exist under
    ``lifecycle/{slug}/`` (``plan.md`` is generated during the session).

    Args:
        items: Backlog items to evaluate.
        all_items: Full backlog set used to resolve ``blocked_by`` references
            (defaults to *items*).
        project_root: Root for relative file paths (defaults to ``Path.cwd()``).
    """
    if all_items is None:
        all_items = items
    if project_root is None:
        project_root = Path.cwd()

    # Build lookup: id → status for blocked-by resolution.
    # Keys are strings (stringified integer IDs) plus UUID entries when present.
    # Both unpadded ("36") and zero-padded ("036") forms are inserted so that
    # blocked-by references using either format resolve correctly.
    status_by_id: dict[str, str] = {}
    for item in all_items:
        status_by_id[str(item.id)] = item.status
        status_by_id[str(item.id).zfill(3)] = item.status
        if item.uuid:
            status_by_id[item.uuid] = item.status

    # Build lookup: id/uuid → slug for BFS blocker-slug resolution.
    # Same dual-key pattern as status_by_id.
    slug_by_id: dict[str, str] = {}
    for item in all_items:
        item_slug = item.resolve_slug()
        slug_by_id[str(item.id)] = item_slug
        slug_by_id[str(item.id).zfill(3)] = item_slug
        if item.uuid:
            slug_by_id[item.uuid] = item_slug

    result = ReadinessResult()

    # Phase 1 — classify items without the blocked check.
    # Items blocked by non-terminal items go into pending_blocked for Phase 2.
    pending_blocked: list[BacklogItem] = []

    for item in items:
        # Gates 1+2 via shared helper; (False, None) sentinel defers to Phase 2 BFS.
        is_ready, reason = is_item_ready(
            item, all_items, eligible_statuses=ELIGIBLE_STATUSES,
            treat_external_blockers_as="blocking")
        if not is_ready:
            if reason is None:
                pending_blocked.append(item)
            else:
                result.ineligible.append(IneligibleItem(item, reason))
            continue

        # 3. Type check — epics are non-implementable
        if item.type == "epic":
            result.ineligible.append(IneligibleItem(item, "epic is non-implementable"))
            continue

        # 4-5. Lifecycle artifact checks — derive paths from lifecycle_slug
        slug = item.resolve_slug()
        research_path = project_root / "cortex" / "lifecycle" / slug / "research.md"
        spec_path = project_root / "cortex" / "lifecycle" / slug / "spec.md"

        if not research_path.exists():
            result.ineligible.append(IneligibleItem(
                item, f"research file not found: lifecycle/{slug}/research.md"
            ))
            continue

        # 5. Spec coverage: per-feature lifecycle spec.md must exist.
        #    plan.md is not required — it is generated during the overnight
        #    session if missing.
        if not spec_path.exists():
            result.ineligible.append(IneligibleItem(
                item, f"spec file not found: lifecycle/{slug}/spec.md"
            ))
            continue

        # 6. Pipeline branch merge check — exclude items whose pipeline branches
        #    are already fully merged into main, regardless of backlog status.
        #    Fails open (treats as eligible) if no branch exists or on errors.
        if _is_pipeline_branch_merged(slug, project_root):
            result.ineligible.append(IneligibleItem(
                item, "pipeline branch already merged into main"
            ))
            continue

        # All checks passed
        if item.spec is None:
            item.spec = f"cortex/lifecycle/{slug}/spec.md"
        result.eligible.append(item)

    # Phase 2 — iterative BFS over pending_blocked.
    # Promote items whose non-terminal blockers are all in the growing
    # session-eligible set (eligible + already-promoted intra_session_blocked).
    session_eligible_slugs: set[str] = {
        item.resolve_slug()
        for item in result.eligible
    }

    promoted = True
    while promoted and pending_blocked:
        promoted = False
        still_pending: list[BacklogItem] = []

        for item in pending_blocked:
            # Compute non-terminal blocker IDs for this item
            blocking_ids = [
                bid for bid in item.blocked_by
                if status_by_id.get(bid, "backlog") not in TERMINAL_STATUSES
            ]

            # Resolve each blocker ID to its slug
            blocker_slugs = [slug_by_id[bid] for bid in blocking_ids if bid in slug_by_id]

            # Unknown blocker IDs (not in slug_by_id) keep the item pending/ineligible
            unknown_ids = [bid for bid in blocking_ids if bid not in slug_by_id]

            if unknown_ids or not all(s in session_eligible_slugs for s in blocker_slugs):
                # Not all blockers are session-eligible yet — keep pending
                still_pending.append(item)
                continue

            # All non-terminal blockers are session-eligible.
            # Still must pass type and artifact checks before promoting.

            # 3. Type check — epics are non-implementable
            if item.type == "epic":
                result.ineligible.append(IneligibleItem(item, "epic is non-implementable"))
                promoted = True  # item resolved (removed from pending)
                continue

            # 4-5. Lifecycle artifact checks
            item_slug = item.resolve_slug()
            research_path = project_root / "cortex" / "lifecycle" / item_slug / "research.md"
            spec_path = project_root / "cortex" / "lifecycle" / item_slug / "spec.md"

            if not research_path.exists():
                result.ineligible.append(IneligibleItem(
                    item, f"research file not found: lifecycle/{item_slug}/research.md"
                ))
                promoted = True
                continue

            if not spec_path.exists():
                result.ineligible.append(IneligibleItem(
                    item, f"spec file not found: lifecycle/{item_slug}/spec.md"
                ))
                promoted = True
                continue

            # Promote to intra_session_blocked
            if item.spec is None:
                item.spec = f"cortex/lifecycle/{item_slug}/spec.md"
            result.intra_session_blocked.append((item, blocker_slugs))
            session_eligible_slugs.add(item_slug)
            promoted = True

        pending_blocked = still_pending

    # Remaining pending_blocked items are genuinely ineligible
    for item in pending_blocked:
        blocking_ids = [
            bid for bid in item.blocked_by
            if status_by_id.get(bid, "backlog") not in TERMINAL_STATUSES
        ]
        ids_str = ", ".join(
            bid.zfill(3) if bid.isdigit() else bid
            for bid in blocking_ids
        )
        result.ineligible.append(IneligibleItem(item, f"blocked by {ids_str} (not in session)"))

    return result


# ---------------------------------------------------------------------------
# Weighted scoring algorithm
# ---------------------------------------------------------------------------

# Component weights (must sum to 1.0)
_W_DEPENDENCY = 0.35
_W_PRIORITY = 0.30
_W_TAG_COHESION = 0.25
_W_TYPE_ROUTING = 0.10

# Priority score map — higher priority items score higher
_PRIORITY_SCORES: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}

# Type routing score map — quick wins (bugs/chores) get a routing boost
_TYPE_SCORES: dict[str, float] = {
    "bug": 1.0,
    "chore": 0.8,
    "feature": 0.5,
    "spike": 0.3,
    "idea": 0.1,
    "epic": 0.0,
}


def _compute_transitive_unblocks(
    items: list[BacklogItem],
) -> dict[int, int]:
    """Count how many items each item transitively unblocks within the set.

    Uses ``blocked_by`` relationships to build a reverse dependency graph
    (item → set of items it directly unblocks), then walks forward from
    each item to count all transitively reachable dependents.

    The ``blocked_by`` field contains string IDs (stringified integers or
    UUIDs). This function maps them back to numeric item IDs for scoring.

    Args:
        items: The eligible item set to analyse.

    Returns:
        Mapping of item ID to count of items it transitively unblocks.
    """
    ids_in_set = {item.id for item in items}

    # Build a lookup from string blocked_by references to numeric item IDs.
    # Supports both stringified integer IDs ("5") and UUIDs.
    str_to_id: dict[str, int] = {}
    for item in items:
        str_to_id[str(item.id)] = item.id
        if item.uuid:
            str_to_id[item.uuid] = item.id

    # Build reverse graph: item_id → set of item IDs it directly unblocks.
    # If item Y has blocked_by=[X], then X directly unblocks Y.
    directly_unblocks: dict[int, set[int]] = {item.id: set() for item in items}
    for item in items:
        for blocker_str in item.blocked_by:
            blocker_id = str_to_id.get(blocker_str)
            if blocker_id is not None and blocker_id in ids_in_set:
                directly_unblocks[blocker_id].add(item.id)

    # For each item, walk the graph to find all transitively unblocked items
    counts: dict[int, int] = {}
    for item_id in ids_in_set:
        visited: set[int] = set()
        stack = list(directly_unblocks[item_id])
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(directly_unblocks.get(current, set()))
        counts[item_id] = len(visited)

    return counts


def _compute_tag_cohesion(items: list[BacklogItem]) -> dict[int, int]:
    """Count how many other items share at least one tag with each item.

    Args:
        items: The eligible item set to analyse.

    Returns:
        Mapping of item ID to count of other items sharing at least one tag.
    """
    # Build inverted index: tag → set of item IDs that have it
    tag_to_items: dict[str, set[int]] = {}
    for item in items:
        for tag in item.tags:
            tag_to_items.setdefault(tag, set()).add(item.id)

    # For each item, collect all other items that share any tag
    cohesion: dict[int, int] = {}
    for item in items:
        peers: set[int] = set()
        for tag in item.tags:
            peers.update(tag_to_items.get(tag, set()))
        # Remove self from peer count
        peers.discard(item.id)
        cohesion[item.id] = len(peers)

    return cohesion


def score_items(
    items: list[BacklogItem],
) -> list[tuple[BacklogItem, float]]:
    """Score eligible backlog items using the hybrid weighted algorithm.

    Components (each normalised 0-1 before weighting):

    - **Dependency structure (0.35)** — items that unblock the most other
      items in the eligible set score higher.
    - **Priority (0.30)** — critical > high > medium > low.
    - **Tag cohesion (0.25)** — items sharing tags with more peers in the
      eligible set score higher (they group well for batching).
    - **Type routing (0.10)** — bugs and chores get a boost as quick wins.

    Final score = 0.35*dep + 0.30*priority + 0.25*tag + 0.10*type.

    Args:
        items: Eligible backlog items to score.

    Returns:
        List of ``(item, score)`` tuples sorted by score descending.
        Ties are broken by item ID ascending for deterministic ordering.
    """
    if not items:
        return []

    # --- Component 1: Dependency structure ---
    dep_counts = _compute_transitive_unblocks(items)
    max_dep = max(dep_counts.values()) if dep_counts else 0

    # --- Component 2: Tag cohesion ---
    tag_counts = _compute_tag_cohesion(items)
    max_tag = max(tag_counts.values()) if tag_counts else 0

    # --- Score each item ---
    scored: list[tuple[BacklogItem, float]] = []
    for item in items:
        # Dependency: normalise by max (0 if max is 0)
        dep_score = dep_counts[item.id] / max_dep if max_dep > 0 else 0.0

        # Priority: direct lookup with fallback
        priority_score = _PRIORITY_SCORES.get(item.priority, 0.5)

        # Tag cohesion: normalise by max (0 if max is 0)
        tag_score = tag_counts[item.id] / max_tag if max_tag > 0 else 0.0

        # Type routing: direct lookup with fallback
        type_score = _TYPE_SCORES.get(item.type, 0.5)

        # Weighted sum
        total = (
            _W_DEPENDENCY * dep_score
            + _W_PRIORITY * priority_score
            + _W_TAG_COHESION * tag_score
            + _W_TYPE_ROUTING * type_score
        )

        scored.append((item, total))

    # Sort by score descending, then by ID ascending for determinism
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    return scored


# ---------------------------------------------------------------------------
# Lead-aware batch grouping
# ---------------------------------------------------------------------------

_QUICK_WIN_TYPES = ("bug", "chore")
_MAX_QUICK_WINS = 2


def _build_batch_context(items: list[BacklogItem]) -> str:
    """Derive a batch_context string from the union of tags in a batch.

    Returns a string like ``"Features in auth, ui subsystems"``.
    If items have no tags, returns ``"General items"``.
    """
    all_tags: list[str] = []
    seen: set[str] = set()
    for item in items:
        for tag in item.tags:
            if tag not in seen:
                seen.add(tag)
                all_tags.append(tag)
    if not all_tags:
        return "General items"
    return f"Features in {', '.join(all_tags)} subsystems"


def _tag_overlap(item: BacklogItem, batch_tags: set[str]) -> int:
    """Count shared tags between an item and a batch's accumulated tag set."""
    return len(set(item.tags) & batch_tags)


def _split_oversized_batch(
    items: list[BacklogItem],
    batch_size_cap: int,
) -> list[list[BacklogItem]]:
    """Split an oversized batch into sub-batches preserving tag locality.

    Groups items by their most common shared tag within the batch, then
    fills sub-batches up to the cap.  Items without tags are distributed
    into the last sub-batch.
    """
    if len(items) <= batch_size_cap:
        return [items]

    # Build tag frequency within this batch to find dominant tags
    tag_freq: dict[str, int] = {}
    for item in items:
        for tag in item.tags:
            tag_freq[tag] = tag_freq.get(tag, 0) + 1

    # Sort tags by frequency descending for deterministic grouping
    sorted_tags = sorted(tag_freq.keys(), key=lambda t: (-tag_freq[t], t))

    # Greedily assign items to sub-groups by dominant tag
    assigned: set[int] = set()
    sub_groups: list[list[BacklogItem]] = []

    for tag in sorted_tags:
        group = [item for item in items if tag in item.tags and item.id not in assigned]
        if not group:
            continue
        for item in group:
            assigned.add(item.id)
        sub_groups.append(group)

    # Collect any unassigned items (no tags)
    remainder = [item for item in items if item.id not in assigned]
    if remainder:
        sub_groups.append(remainder)

    # Now merge small sub-groups and split large ones to respect cap
    final_batches: list[list[BacklogItem]] = []
    current: list[BacklogItem] = []

    for group in sub_groups:
        if len(current) + len(group) <= batch_size_cap:
            current.extend(group)
        else:
            # Flush current if non-empty
            if current:
                final_batches.append(current)
                current = []
            # If this group itself exceeds cap, chunk it
            if len(group) > batch_size_cap:
                for i in range(0, len(group), batch_size_cap):
                    chunk = group[i:i + batch_size_cap]
                    final_batches.append(chunk)
            else:
                current = list(group)

    if current:
        final_batches.append(current)

    return final_batches


def group_into_batches(
    scored_items: list[tuple[BacklogItem, float]],
    batch_size_cap: int = 5,
) -> list[Batch]:
    """Group scored backlog items into batches.

    The algorithm has three phases:

    1. **Quick wins** — extract up to 2 items with type ``bug`` or ``chore``
       into the first batch regardless of tags.
    2. **Greedy tag assignment** — for each remaining item (in score order),
       assign it to the existing batch with the most tag overlap.  Ties are
       broken by picking the batch with fewer items.  If no batch has any
       tag overlap, start a new batch.
    3. **Split oversized batches** — any batch exceeding *batch_size_cap*
       is split while preserving tag locality within splits.

    Each batch receives a ``batch_context`` string describing its knowledge
    domain (derived from the union of tags) and a 1-based ``batch_id``.

    Args:
        scored_items: List of ``(BacklogItem, score)`` tuples, already
            sorted by score descending (output of :func:`score_items`).
        batch_size_cap: Maximum number of items per batch.  Defaults to 5.

    Returns:
        List of :class:`Batch` instances ordered by batch_id.
    """
    if not scored_items:
        return []

    # --- Phase 1: Extract quick wins ---
    quick_wins: list[BacklogItem] = []
    remaining: list[BacklogItem] = []

    for item, _score in scored_items:
        if item.type in _QUICK_WIN_TYPES and len(quick_wins) < _MAX_QUICK_WINS:
            quick_wins.append(item)
        else:
            remaining.append(item)

    # Quick wins form a standalone first batch — they are fast items that
    # don't need deep context, so they are NOT included in Phase 2's tag-
    # overlap assignment.  Phase 2 builds new batches for the remaining items.
    batches: list[tuple[list[BacklogItem], set[str]]] = []

    # --- Phase 2: Greedy tag assignment ---
    for item in remaining:
        best_idx = -1
        best_overlap = 0
        best_size = float("inf")

        item_tags = set(item.tags)
        item_areas = set(item.areas)

        for idx, (batch_items, batch_tags) in enumerate(batches):
            # Area-separation pre-filter: if the incoming item and any item
            # already in this batch share at least one area, skip the batch
            # to force area-overlapping items into separate rounds.
            if item_areas:
                batch_areas: set[str] = set()
                for bi in batch_items:
                    batch_areas.update(bi.areas)
                if batch_areas & item_areas:
                    continue

            overlap = len(item_tags & batch_tags)
            if overlap > best_overlap or (
                overlap == best_overlap
                and overlap > 0
                and len(batch_items) < best_size
            ):
                best_overlap = overlap
                best_idx = idx
                best_size = len(batch_items)

        if best_overlap > 0 and best_idx >= 0:
            # Assign to the best-matching batch
            batches[best_idx][0].append(item)
            batches[best_idx][1].update(item_tags)
        else:
            # No overlap with any existing batch — start a new one
            batches.append(([item], set(item_tags)))

    # --- Phase 3: Split oversized batches ---
    split_batches: list[list[BacklogItem]] = []
    for batch_items, _tags in batches:
        if len(batch_items) <= batch_size_cap:
            split_batches.append(batch_items)
        else:
            splits = _split_oversized_batch(batch_items, batch_size_cap)
            split_batches.extend(splits)

    # Prepend quick-win batch (if any) so it is always batch 1
    final_batches: list[list[BacklogItem]] = []
    if quick_wins:
        final_batches.append(quick_wins)
    final_batches.extend(split_batches)

    # --- Build Batch dataclass instances ---
    result: list[Batch] = []
    for idx, batch_items in enumerate(final_batches, start=1):
        result.append(Batch(
            items=batch_items,
            batch_context=_build_batch_context(batch_items),
            batch_id=idx,
        ))

    return result


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def select_overnight_batch(
    backlog_dir: Path = DEFAULT_BACKLOG_DIR,
    batch_size_cap: int = 5,
) -> SelectionResult:
    """Select and group backlog items for overnight execution.

    Composes the full pipeline: parse → filter → score → group.
    This is the single entry point the overnight orchestrator calls.

    Args:
        backlog_dir: Path to the backlog directory.
        batch_size_cap: Maximum items per batch.

    Returns:
        A :class:`SelectionResult` with batches, ineligible items,
        and a human-readable summary.
    """
    try:
        all_items = load_from_index(backlog_dir)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        import warnings
        warnings.warn(f"index.json unavailable ({exc}), falling back to file reads")
        all_items = parse_backlog_dir(backlog_dir)
    readiness = filter_ready(all_items, all_items=all_items)

    if readiness.eligible:
        scored = score_items(readiness.eligible)
        batches = group_into_batches(scored, batch_size_cap)
    else:
        batches = []

    # BFS round assignment for intra-session blocked items
    intra_session_deps: dict[str, list[str]] = {}

    if readiness.intra_session_blocked:
        # Build slug → batch_id map from independent batches
        slug_to_batch_id: dict[str, int] = {}
        for batch in batches:
            for item in batch.items:
                slug_to_batch_id[item.resolve_slug()] = batch.batch_id

        # Build batches_by_id for merge-into-existing-batch
        batches_by_id: dict[int, Batch] = {b.batch_id: b for b in batches}

        # BFS queue of (item, blocker_slugs)
        queue: list[tuple[BacklogItem, list[str]]] = list(readiness.intra_session_blocked)

        while queue:
            next_queue: list[tuple[BacklogItem, list[str]]] = []
            promoted_this_round = 0

            for item, blocker_slugs in queue:
                if all(s in slug_to_batch_id for s in blocker_slugs):
                    # All blockers assigned — place this item in round after the latest blocker
                    batch_id = max(slug_to_batch_id[s] for s in blocker_slugs) + 1
                    if batch_id in batches_by_id:
                        batches_by_id[batch_id].items.append(item)
                    else:
                        new_batch = Batch(batch_id=batch_id, items=[item])
                        batches.append(new_batch)
                        batches_by_id[batch_id] = new_batch
                    dep_slug = item.resolve_slug()
                    slug_to_batch_id[dep_slug] = batch_id
                    intra_session_deps[dep_slug] = blocker_slugs
                    promoted_this_round += 1
                else:
                    next_queue.append((item, blocker_slugs))

            if promoted_this_round == 0:
                # No progress — all remaining items are in a dependency cycle
                for item, _blocker_slugs in next_queue:
                    readiness.ineligible.append(IneligibleItem(item, "circular dependency"))
                break

            queue = next_queue

    # Build summary
    n_eligible = len(readiness.eligible)
    n_ineligible = len(readiness.ineligible)
    n_batches = len(batches)
    total_selected = sum(len(b.items) for b in batches)

    lines: list[str] = []
    lines.append(
        f"Selected {total_selected} items in {n_batches} batches "
        f"from {n_eligible} eligible "
        f"({n_ineligible} ineligible — run /discovery first)"
    )
    lines.append("")

    for batch in batches:
        titles = ", ".join(item.title for item in batch.items)
        lines.append(f"Batch {batch.batch_id} ({batch.batch_context}): {titles}")

    if readiness.ineligible:
        lines.append("")
        reasons = ", ".join(
            f"{item.title} ({reason})"
            for item, reason in readiness.ineligible
        )
        lines.append(f"Not ready: {reasons}")

    summary = "\n".join(lines)

    return SelectionResult(
        batches=batches,
        ineligible=readiness.ineligible,
        summary=summary,
        intra_session_deps=intra_session_deps,
    )
