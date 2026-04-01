"""Session plan renderer for overnight orchestration.

Renders a markdown session plan from a SelectionResult, summarising
which features will be executed, in what order, and any risk factors.
The plan is presented to the user for approval before overnight
execution begins.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from claude.common import atomic_write, slugify
from claude.overnight.backlog import BacklogItem, Batch, SelectionResult
from claude.overnight.state import OvernightFeatureStatus, OvernightState, save_state, session_dir

_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"

DEFAULT_PLAN_PATH = _LIFECYCLE_ROOT / "overnight-plan.md"


def _format_item_row(
    round_num: int,
    item: BacklogItem,
    depends_on: str = "-",
) -> str:
    """Format a single BacklogItem as a markdown table row."""
    return (
        f"| {round_num} "
        f"| {item.title} "
        f"| {item.id:03d} "
        f"| {item.type} "
        f"| {item.priority} "
        f"| research + spec "
        f"| {depends_on} |"
    )


def _detect_risks(batches: list[Batch]) -> list[str]:
    """Detect risks from batch metadata.

    Checks for:
    - Batches with shared parent epics (items from different batches
      sharing a parent ID).
    - Overlapping tags across batches (tags appearing in more than one
      batch, indicating potential file overlap).
    """
    risks: list[str] = []

    if len(batches) < 2:
        return risks

    # Check for shared parent epics across batches
    parents_by_batch: list[set[int]] = []
    for batch in batches:
        parents = {item.parent for item in batch.items if item.parent is not None}
        parents_by_batch.append(parents)

    for i in range(len(parents_by_batch)):
        for j in range(i + 1, len(parents_by_batch)):
            shared = parents_by_batch[i] & parents_by_batch[j]
            if shared:
                ids_str = ", ".join(f"#{p.zfill(3) if p.isdigit() else p}" for p in sorted(shared))
                risks.append(
                    f"Batches {batches[i].batch_id} and {batches[j].batch_id} "
                    f"share parent epic(s) {ids_str} -- potential file overlap"
                )

    # Check for overlapping tags across batches
    tags_by_batch: list[set[str]] = []
    for batch in batches:
        tags: set[str] = set()
        for item in batch.items:
            tags.update(item.tags)
        tags_by_batch.append(tags)

    for i in range(len(tags_by_batch)):
        for j in range(i + 1, len(tags_by_batch)):
            shared = tags_by_batch[i] & tags_by_batch[j]
            if shared:
                tags_str = ", ".join(sorted(shared))
                risks.append(
                    f"Batches {batches[i].batch_id} and {batches[j].batch_id} "
                    f"share tags [{tags_str}] -- review for dependency concerns"
                )

    return risks


def validate_target_repos(selection: SelectionResult) -> list[str]:
    """Validate that all repo: paths in a SelectionResult are accessible git repos.

    Collects unique non-null repo values from all items in selection.batches,
    expands ~ via os.path.expanduser(), and runs ``git rev-parse
    --is-inside-work-tree`` for each path to confirm it is a git repository.

    Args:
        selection: The SelectionResult whose batched items will be checked.

    Returns:
        A list of raw (unexpanded) repo strings that failed validation.
        Returns an empty list if all repos are accessible or no repos are set.
    """
    seen: set[str] = set()
    failures: list[str] = []

    for batch in selection.batches:
        for item in batch.items:
            if item.repo is None:
                continue
            expanded = os.path.expanduser(item.repo)
            if expanded in seen:
                continue
            seen.add(expanded)
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=expanded,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    failures.append(item.repo)
            except (FileNotFoundError, OSError):
                failures.append(item.repo)

    return failures


def render_session_plan(
    selection: SelectionResult,
    concurrency: int = 2,
    time_limit_hours: int = 6,
    date: str | None = None,
) -> str:
    """Render a session plan as a markdown string.

    Args:
        selection: The SelectionResult from the backlog readiness gate.
        concurrency: Number of features executed in parallel per round.
        time_limit_hours: Maximum wall-clock hours for the session.
        date: Date string for the plan header (YYYY-MM-DD). Defaults to
            today's date.

    Returns:
        The complete session plan as a markdown string.
    """
    if date is None:
        from datetime import date as date_cls

        date = date_cls.today().isoformat()

    total_items = sum(len(b.items) for b in selection.batches)
    num_rounds = len(selection.batches)
    est_minutes = num_rounds * 45  # rough estimate: 45 min per round

    lines: list[str] = []

    # Header
    lines.append(f"# Overnight Session Plan: {date}")
    lines.append("")

    # Build slug → display ID map for dependency cross-references
    slug_to_id: dict[str, str] = {}
    for batch in selection.batches:
        for item in batch.items:
            item_slug = item.lifecycle_slug or slugify(item.title)
            slug_to_id[item_slug] = f"#{item.id:03d}" if item.id else item_slug

    # Selected Features table
    lines.append(f"## Selected Features ({total_items})")
    lines.append("")
    lines.append(
        "| Round | Feature | Backlog # | Type | Priority | Pre-work Status | Depends On |"
    )
    lines.append(
        "|-------|---------|-----------|------|----------|-----------------|------------|"
    )

    for batch in selection.batches:
        for item in batch.items:
            dep_slug = item.lifecycle_slug or slugify(item.title)
            if dep_slug in selection.intra_session_deps:
                blocker_ids = ", ".join(
                    slug_to_id.get(s, s)
                    for s in selection.intra_session_deps[dep_slug]
                )
                depends_on = blocker_ids
            else:
                depends_on = "-"
            lines.append(_format_item_row(batch.batch_id, item, depends_on=depends_on))

    lines.append("")

    # Execution Strategy
    lines.append("## Execution Strategy")
    lines.append("")
    lines.append(f"- **Rounds**: {num_rounds}")
    lines.append(f"- **Concurrency**: {concurrency} features per round")
    lines.append(f"- **Estimated duration**: ~{est_minutes} minutes")
    lines.append(f"- **Time limit**: {time_limit_hours} hours")
    lines.append("")

    # Not Ready section — exclude terminal items (complete, done, etc.) which are
    # finished work, not items genuinely blocked from overnight execution.
    _TERMINAL = frozenset(("complete", "done", "resolved", "wontfix", "abandoned"))
    actionable = [
        (item, reason) for item, reason in selection.ineligible
        if item.status not in _TERMINAL
    ]
    lines.append(f"## Not Ready ({len(actionable)})")
    lines.append("")
    if actionable:
        for item, reason in actionable:
            lines.append(f"- **{item.title}** (#{item.id:03d}): {reason}")
    else:
        lines.append("- All scanned items passed readiness checks")
    lines.append("")

    # Risks
    lines.append("## Risks")
    lines.append("")
    risks = _detect_risks(selection.batches)
    if risks:
        for risk in risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- No cross-batch dependency or file overlap risks detected")
    lines.append("")

    # Stop Conditions
    lines.append("## Stop Conditions")
    lines.append("")
    lines.append("- Zero progress detected in a round (no features advance)")
    lines.append(f"- Wall-clock time exceeds {time_limit_hours} hours")
    lines.append("")

    return "\n".join(lines)


def write_session_plan(
    content: str,
    plan_dir: Path | None = None,
) -> Path:
    """Atomically write the session plan markdown to disk.

    Uses a tempfile + os.replace pattern so readers never see a
    partially-written file.

    Args:
        content: The rendered session plan markdown string.
        plan_dir: Directory to write ``overnight-plan.md`` into.
            Defaults to the parent of ``DEFAULT_PLAN_PATH`` for
            backward compatibility during the transition to
            session directories.

    Returns:
        The path the plan was written to.
    """
    if plan_dir is None:
        plan_dir = DEFAULT_PLAN_PATH.parent

    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "overnight-plan.md"
    atomic_write(plan_path, content)
    return plan_path


def write_session_manifest(
    session_id: str,
    session_type: str,
    features: list[str],
    session_dir: Path,
) -> None:
    """Atomically write a session manifest to disk.

    Creates ``session_dir / "session.json"`` containing the session
    metadata. Uses the same atomic write pattern as other artifact
    producers.

    Args:
        session_id: Unique session identifier (e.g.
            ``"overnight-2026-03-02-2200"``).
        session_type: Session type label (``"overnight"`` or
            ``"pipeline"``).
        features: List of feature slugs included in this session.
        session_dir: Directory to write ``session.json`` into.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "type": session_type,
        "session_id": session_id,
        "started": datetime.now(timezone.utc).isoformat(),
        "features": features,
    }
    payload = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    atomic_write(session_dir / "session.json", payload)


def initialize_overnight_state(
    selection: SelectionResult,
    plan_content: str | None = None,
) -> OvernightState:
    """Create the initial OvernightState from an approved session plan.

    Takes a ``SelectionResult`` (the output of the backlog selection
    pipeline after user approval) and builds the overnight state with
    all selected features in ``pending`` status.

    The session ID is a human-readable timestamp:
    ``overnight-YYYY-MM-DD-HHmm`` (UTC).

    Args:
        selection: The approved SelectionResult containing batches of
            features to execute overnight.
        plan_content: The rendered session plan markdown string (the
            output of ``render_session_plan()``). When provided, its
            SHA-256 digest is stored as ``OvernightState.plan_hash``
            and used as the stable component in per-task idempotency
            tokens. Pass ``None`` only in tests or legacy callers that
            do not need idempotency tokens.

    Returns:
        A fully-initialised OvernightState ready for the orchestrator
        to begin execution. The caller is responsible for persisting
        the state via ``save_state()``.
    """
    session_id = datetime.now(timezone.utc).strftime("overnight-%Y-%m-%d-%H%M")

    # Collision-avoidance: if a session directory already exists for this
    # timestamp, append an incrementing suffix until a free name is found.
    # Uses os.path.exists() on the resolved string path so that test patches
    # targeting pathlib.Path.exists (for worktree collision tests) do not
    # interfere with this loop.
    suffix = 0
    base_id = session_id
    while os.path.exists(session_dir(session_id)):
        suffix += 1
        session_id = f"{base_id}-{suffix}"

    plan_hash = (
        hashlib.sha256(plan_content.encode("utf-8")).hexdigest()
        if plan_content is not None
        else None
    )

    # Create a git worktree for this session in $TMPDIR so the user's working
    # tree stays on the current branch throughout overnight execution.
    worktree_path = Path(os.environ.get("TMPDIR", "/tmp")) / "overnight-worktrees" / session_id
    # Prune stale worktree metadata, then remove any leftover directory, before
    # creating the new worktree (handles the case where a previous run left an
    # orphaned worktree at the same path).
    subprocess.run(["git", "worktree", "prune"])
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)

    # Clean up any orphaned branch from a previous failed run before creating
    # the worktree (git worktree add -b fails if the branch already exists).
    integration_branch_name = f"overnight/{session_id}"
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{integration_branch_name}"],
    )
    if result.returncode == 0:
        try:
            subprocess.run(
                ["git", "branch", "-D", integration_branch_name],
                check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"Branch {integration_branch_name} exists and could not be "
                f"deleted — a live session may be running."
            )

    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", integration_branch_name],
        check=True,
    )

    project_root = str(Path.cwd().resolve())
    integration_branches: dict[str, str] = {project_root: integration_branch_name}

    features: dict[str, OvernightFeatureStatus] = {}
    for batch in selection.batches:
        for item in batch.items:
            slug = item.lifecycle_slug or slugify(item.title)
            features[slug] = OvernightFeatureStatus(
                status="pending",
                round_assigned=batch.batch_id,
                spec_path=item.spec,
                plan_path=item.plan if item.plan else f"lifecycle/{slug}/plan.md",
                backlog_id=item.id if item.id else None,
                repo_path=item.repo,
            )
            features[slug].intra_session_blocked_by = selection.intra_session_deps.get(slug, [])
            if item.repo is not None:
                repo_key = str(Path(item.repo).expanduser().resolve())
                integration_branches[repo_key] = integration_branch_name

    # Create a git integration worktree for each unique cross-repo target.
    # Skip the home repo (already has a worktree created above).
    integration_worktrees: dict[str, str] = {}
    for repo_path, branch_name in integration_branches.items():
        if repo_path == project_root:
            continue

        cross_worktree_path = (
            Path(os.environ.get("TMPDIR", "/tmp"))
            / "overnight-worktrees"
            / f"{session_id}-{Path(repo_path).name}"
        )

        # Resolve the base ref for this repo (origin/HEAD, falling back to origin/main).
        base_ref_result = subprocess.run(
            ["git", "rev-parse", "origin/HEAD"],
            cwd=repo_path,
            capture_output=True,
        )
        if base_ref_result.returncode == 0 and base_ref_result.stdout.strip():
            base_ref = base_ref_result.stdout.decode().strip()
        else:
            base_ref = "origin/main"

        # Stale cleanup: prune, rmtree, show-ref + branch -D.
        try:
            subprocess.run(["git", "worktree", "prune"], cwd=repo_path)
        except Exception:
            print(
                f"Warning: git worktree prune failed for {repo_path}",
                file=sys.stderr,
            )

        if Path(cross_worktree_path).exists():
            shutil.rmtree(cross_worktree_path)

        ref_check = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
            cwd=repo_path,
        )
        if ref_check.returncode == 0:
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=repo_path,
                check=True,
            )

        # Create the integration worktree for this cross-repo target.
        try:
            subprocess.run(
                [
                    "git", "worktree", "add",
                    str(cross_worktree_path),
                    "-b", branch_name,
                    base_ref,
                ],
                cwd=repo_path,
                check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"Failed to create integration worktree for {repo_path}"
            )

        integration_worktrees[repo_path] = str(cross_worktree_path)

    # Pure wild-light routing: when the session targets exactly one
    # cross-repo and has NO home-repo-local features, make that cross-repo worktree
    # the primary worktree_path and store the home-repo worktree in
    # integration_worktrees so ticket 1075 can still locate it.
    # Mixed sessions (home + cross-repo) always use the home-repo worktree as primary.
    has_home_features = any(
        item.repo is None
        for batch in selection.batches
        for item in batch.items
    )
    if len(integration_worktrees) == 1 and not has_home_features:
        primary_repo_key = next(iter(integration_worktrees))
        primary_worktree_str = integration_worktrees[primary_repo_key]
        integration_worktrees[project_root] = str(worktree_path)
    else:
        primary_worktree_str = str(worktree_path)

    return OvernightState(
        session_id=session_id,
        plan_ref=str(DEFAULT_PLAN_PATH),
        plan_hash=plan_hash,
        phase="executing",
        features=features,
        integration_branch=f"overnight/{session_id}",
        integration_branches=integration_branches,
        worktree_path=primary_worktree_str,
        project_root=project_root,
        integration_worktrees=integration_worktrees,
    )


def bootstrap_session(
    selection: SelectionResult,
    plan_content: str,
) -> tuple[OvernightState, Path]:
    """Initialize a complete overnight session from a selection and plan.

    Collapses the five discrete initialization steps into a single call:
    create state, resolve session directory, write plan, write manifest,
    and persist state.

    Note: ``initialize_overnight_state`` (step a) creates a git worktree as
    a side effect.  If any subsequent step (b--e) raises, that worktree is a
    resource leak.  The caller must run ``git worktree prune`` on exception
    to reclaim it (the session ID is unknown at the call site on failure, so
    targeted removal is not possible).

    Args:
        selection: The batch selection result containing features to execute.
        plan_content: Rendered session-plan markdown string.

    Returns:
        A ``(state, state_dir)`` tuple where *state* is the fully-populated
        ``OvernightState`` and *state_dir* is the ``Path`` to the session
        directory on disk.
    """
    state = initialize_overnight_state(selection, plan_content=plan_content)
    state_dir = session_dir(state.session_id)
    write_session_plan(plan_content, plan_dir=state_dir)
    write_session_manifest(
        session_id=state.session_id,
        session_type="overnight",
        features=list(state.features),
        session_dir=state_dir,
    )
    save_state(state, state_dir / "overnight-state.json")
    return (state, state_dir)


def extract_spec_section(
    item_id: int,
    spec_path: str,
    slug: str,
    project_root: Path,
) -> Path:
    """Extract a per-feature spec section from a batch spec and write it to disk.

    Reads the batch spec at ``project_root / spec_path``, splits it into
    top-level ``## `` sections, and partitions them into:

    - **Item-specific**: any section that contains the tag ``(NNN)`` where
      NNN is ``item_id`` zero-padded to three digits.  Within these sections,
      only lines that contain the tag or are not numbered/bulleted list items
      are kept (prose, headings, and blank lines are always preserved).
    - **Shared context**: all other sections, copied verbatim.

    The output file begins with a provenance header identifying the source
    batch spec and item tag, followed by shared sections then item-specific
    sections.

    Args:
        item_id: Numeric backlog item ID (e.g. 56).
        spec_path: Relative path to the batch spec (e.g.
            ``"research/pipeline-and-tooling-polish/spec.md"``).
        slug: Kebab-case slug for the feature (e.g.
            ``"improve-validate-skill-py-yaml-error-messages"``).
        project_root: Repository root for resolving relative paths.

    Returns:
        Path of the written ``lifecycle/{slug}/spec.md`` file.
    """
    tag = f"({item_id:03d})"
    batch_spec_text = (project_root / spec_path).read_text(encoding="utf-8")

    # Split into top-level sections at "## " boundaries.
    # re.split with a lookahead preserves the "## " delimiter at the start
    # of each element (except possibly a leading non-section preamble).
    raw_parts = re.split(r"(?=^## )", batch_spec_text, flags=re.MULTILINE)

    shared_parts: list[str] = []
    item_parts: list[str] = []

    for part in raw_parts:
        if not part.strip():
            continue
        if tag in part:
            # Item-specific section: filter out list items that lack the tag.
            # A list item line starts with optional whitespace followed by
            # a digit+period or a dash/asterisk and a space.
            filtered_lines: list[str] = []
            for line in part.splitlines(keepends=True):
                is_list_item = bool(re.match(r"^\s*(\d+\.|-|\*)\s", line))
                if not is_list_item or tag in line:
                    filtered_lines.append(line)
            item_parts.append("".join(filtered_lines))
        else:
            shared_parts.append(part)

    # Build provenance header
    shared_headings = [
        m.group(1)
        for part in shared_parts
        for m in [re.match(r"^## (.+)", part.lstrip())]
        if m
    ]
    header_note = (
        f"> Extracted from batch spec: {spec_path} (item {tag})\n"
        f"> Shared sections included: "
        f"{', '.join(shared_headings) if shared_headings else 'none'}\n\n"
    )

    # Compose output: provenance header, then shared sections, then item sections
    sections = [header_note]
    for part in shared_parts:
        sections.append(part.rstrip() + "\n\n")
    for part in item_parts:
        sections.append(part.rstrip() + "\n\n")

    output = "".join(sections)

    dest = project_root / "lifecycle" / slug / "spec.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(output, encoding="utf-8")
    return dest


def extract_batch_specs(
    state: "OvernightState",
    project_root: Path,
) -> list[Path]:
    """Extract per-feature lifecycle specs for batch-spec items in the session.

    Iterates over all features in ``state``.  For each feature that has a
    ``spec_path`` (batch spec) but no existing ``lifecycle/{slug}/spec.md``,
    calls :func:`extract_spec_section` to write the per-feature spec.

    Features with an existing lifecycle spec, no ``spec_path``, or no
    ``backlog_id`` are skipped silently.

    Args:
        state: The initialized overnight session state.
        project_root: Repository root for resolving relative paths.

    Returns:
        List of paths for newly written ``lifecycle/{slug}/spec.md`` files.
        Empty if no extraction was needed.
    """
    created: list[Path] = []
    for slug, feature_status in state.features.items():
        # Skip if per-feature lifecycle spec already exists
        if (project_root / "lifecycle" / slug / "spec.md").exists():
            continue
        # Skip if no batch spec or no backlog ID to identify the section
        if not feature_status.spec_path or feature_status.backlog_id is None:
            continue
        dest = extract_spec_section(
            item_id=feature_status.backlog_id,
            spec_path=feature_status.spec_path,
            slug=slug,
            project_root=project_root,
        )
        created.append(dest)
    return created
