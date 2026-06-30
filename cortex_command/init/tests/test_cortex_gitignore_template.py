"""Pattern-correctness tests for the shipped ``cortex/.gitignore`` template.

Materializes the shipped template into a throwaway git repo and asserts the
``git check-ignore --no-index`` matrix from Spec Req 1 (transient artifacts
ignored at active AND archive depth) and Req 2 (must-track work-products never
ignored, even at archive depth). ``--no-index`` makes this a pure pattern test
that ignores tracked-file precedence, so it pins the depth-complete-but-narrow
contract independent of any repo's tracking state.

The matrix is deliberately extended past the spec's enumerated paths to probe
archive depth for EVERY widened rule — not just the two the spec enumerates —
so a regression that leaves any rule single-level (``lifecycle/*/...``) is
caught here rather than silently passing the narrower spec matrix.
"""

from __future__ import annotations

import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

# Source the shipped template bytes from the same package resource handle the
# scaffolder uses (``_TEMPLATE_ROOT``), never a hardcoded copy.
_TEMPLATE_BYTES = (
    files("cortex_command.init.templates").joinpath("cortex/.gitignore").read_bytes()
)


# Transient artifacts — every entry MUST be ignored (check-ignore exit 0).
# Active-feature depth (lifecycle/<slug>/...) and archive depth
# (lifecycle/archive/<slug>/...) are both probed for each widened rule.
_IGNORED = [
    # critical-review residue — active + archive (Spec Req 1)
    "cortex/lifecycle/feat/critical-review-residue.json",
    "cortex/lifecycle/archive/x/critical-review-residue.json",
    # transient refine->research considerations input — active + archive (#337)
    "cortex/lifecycle/feat/research-considerations.md",
    "cortex/lifecycle/archive/x/research-considerations.md",
    # session / lock files — active + archive
    "cortex/lifecycle/feat/.session",
    "cortex/lifecycle/archive/x/.session",
    "cortex/lifecycle/feat/.session-owner",
    "cortex/lifecycle/archive/x/.session-owner",
    "cortex/lifecycle/feat/.lock",
    "cortex/lifecycle/archive/x/.lock",
    "cortex/lifecycle/feat/.dispatching",
    "cortex/lifecycle/archive/x/.dispatching",
    # runtime activity log — active + archive
    "cortex/lifecycle/feat/agent-activity.jsonl",
    "cortex/lifecycle/archive/x/agent-activity.jsonl",
    # narrow learnings rule — recovery-log.md at active + archive depth
    "cortex/lifecycle/feat/learnings/recovery-log.md",
    "cortex/lifecycle/archive/x/learnings/recovery-log.md",
    # single-level lifecycle artifacts (no archive depth by design)
    "cortex/lifecycle/overnight-events.log",
    "cortex/lifecycle/overnight-events-2026-06.log",
    "cortex/lifecycle/metrics.json",
    "cortex/lifecycle/sessions/run-1.json",
    # backlog audit log + regenerated index cache
    "cortex/backlog/items.events.jsonl",
    "cortex/backlog/index.json",
    "cortex/backlog/index.md",
    # ad-hoc critical-review snapshots
    "cortex/_adhoc/snapshot.json",
]

# Must-track work-products — every entry MUST NOT be ignored (exit 1). The
# archive-depth learnings/outline.md case proves the narrow recovery-log.md
# rule does not over-match sibling work-products at archive depth.
_NOT_IGNORED = [
    "cortex/backlog/x.md",
    "cortex/lifecycle/feat/spec.md",
    "cortex/lifecycle/archive/x/spec.md",
    "cortex/lifecycle/feat/research.md",
    "cortex/lifecycle/feat/plan.md",
    "cortex/lifecycle/feat/index.md",
    "cortex/lifecycle/feat/events.log",
    "cortex/lifecycle/feat/learnings/outline.md",
    "cortex/lifecycle/archive/x/learnings/outline.md",
    "cortex/requirements/project.md",
    "cortex/adr/x.md",
]


@pytest.fixture
def gitignore_repo(tmp_path: Path) -> Path:
    """A throwaway git repo carrying only the shipped ``cortex/.gitignore``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    gitignore = repo / "cortex" / ".gitignore"
    gitignore.parent.mkdir(parents=True)
    gitignore.write_bytes(_TEMPLATE_BYTES)
    return repo


def _check_ignore(repo: Path, rel_path: str) -> int:
    """Return the ``git check-ignore --no-index`` exit code for ``rel_path``.

    ``--no-index`` makes the call a pure pattern test (0 = a rule matches,
    1 = no rule matches) regardless of whether the path is tracked.
    """
    return subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", rel_path],
        cwd=repo,
        capture_output=True,
    ).returncode


@pytest.mark.parametrize("rel_path", _IGNORED)
def test_transient_artifacts_ignored(gitignore_repo: Path, rel_path: str) -> None:
    """Spec Req 1: transient artifacts are ignored at active AND archive depth."""
    assert _check_ignore(gitignore_repo, rel_path) == 0, (
        f"expected {rel_path!r} to be ignored by the shipped cortex/.gitignore"
    )


@pytest.mark.parametrize("rel_path", _NOT_IGNORED)
def test_must_track_never_ignored(gitignore_repo: Path, rel_path: str) -> None:
    """Spec Req 2: work-products are never ignored, even at archive depth."""
    assert _check_ignore(gitignore_repo, rel_path) == 1, (
        f"expected {rel_path!r} to NOT be ignored by the shipped cortex/.gitignore"
    )
