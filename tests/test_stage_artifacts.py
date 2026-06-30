"""Real-git staged-set coverage for ``cortex-lifecycle-stage-artifacts``.

Pins the per-phase staged set the ``cortex_command.lifecycle.stage_artifacts``
verb produces by building a real git fixture repo (the ``_git`` harness ported
from ``tests/test_revert_merge_real_git.py``) and asserting that the *live* git
index — sorted ``git diff --cached --name-only`` — equals the expected set for
each ``--phase`` / sub-mode. The verb's self-reported ``staged_paths`` is
asserted against the same hardcoded expected set, so neither assertion trusts
the other.

Coverage map (spec #331 Reqs 9-13):

* Req 9  — ``--phase complete`` full set + ``--phase refine`` approval/cancel
  sets;
* Req 10 — refine approval (``spec.md`` staged) vs cancel (``spec.md`` omitted
  even though it is present on disk — discriminating);
* Req 11 — backlog write-back: resolved ticket file + ``index.md`` staged on a
  resolvable ticket; an exit-3 (no-match) fixture stages neither and the verb
  still exits 0;
* Req 12 — the ``staged`` / ``nothing_staged`` signal matches
  ``git diff --cached --quiet``'s exit on a real stage vs a no-op re-run;
* Req 13 — the negative-token controls from
  ``tests/test_complete_md_finalization_commit.py:21-35`` ported as staged-set
  exclusions: unrelated *dirty tracked* files under ``cortex/lifecycle/`` and
  ``cortex/requirements/`` (the dropped directory/`-u` sweep) and the bug-2
  no-sweep control ``cortex/backlog/OTHER.md``. Each control is verified to be
  genuinely dirty (would be caught by ``git add -u``) yet absent from the index.

The negative controls are *behavioral* (git-index exclusions), not source
string-greps — they exercise the verb's explicit-enumerate-no-glob discipline
against a working tree the dropped sweep would have over-captured.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from cortex_command.lifecycle.stage_artifacts import main, stage

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

SLUG = "my-feature"
LC = f"cortex/lifecycle/{SLUG}"
# Backlog filename slug is a prefix-EXTENSION of the lifecycle slug — so the
# resolver must match via the ticket's ``lifecycle_slug:`` frontmatter (kebab
# strip leaves ``my-feature-with-extra-detail`` != ``my-feature``), mirroring
# the real truncated-prefix case the verb's docstring calls out.
TICKET = "007-my-feature-with-extra-detail.md"
TICKET_REL = f"cortex/backlog/{TICKET}"

LIFECYCLE_COMPLETE = sorted(
    [
        f"{LC}/research.md",
        f"{LC}/spec.md",
        f"{LC}/plan.md",
        f"{LC}/review.md",
        f"{LC}/index.md",
        f"{LC}/events.log",
    ]
)


# ---------------------------------------------------------------------------
# Real-git harness (ported from tests/test_revert_merge_real_git.py:51-106)
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run git with a repeatable identity inside a fixture repo."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
    }
    env.pop("GIT_DIR", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _new_repo(root: Path) -> None:
    """Initialise a throwaway repo with hooks/gpgsign off and a pinned identity."""
    _git("init", "-b", "main", ".", cwd=root)
    _git("config", "core.hooksPath", "/dev/null", cwd=root)
    _git("config", "commit.gpgsign", "false", cwd=root)
    _git("config", "tag.gpgsign", "false", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _commit_all(root: Path, msg: str) -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-m", msg, cwd=root)


def _staged(root: Path) -> list[str]:
    """The live staged set — sorted ``git diff --cached --name-only``."""
    out = _git("diff", "--cached", "--name-only", cwd=root).stdout
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def _unstaged(root: Path) -> list[str]:
    """Tracked-but-unstaged (dirty working-tree) files — sorted."""
    out = _git("diff", "--name-only", cwd=root).stdout
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def _diff_cached_quiet_exit(root: Path) -> int:
    """``git diff --cached --quiet`` exit code (0 == nothing staged, 1 == staged)."""
    return _git("diff", "--cached", "--quiet", cwd=root, check=False).returncode


# ---------------------------------------------------------------------------
# Content builders
# ---------------------------------------------------------------------------


def _write_ticket(
    root: Path,
    filename: str = TICKET,
    lifecycle_slug: str = SLUG,
    title: str = "My feature with extra detail",
) -> None:
    _write(
        root,
        f"cortex/backlog/{filename}",
        f"---\ntitle: {title}\nlifecycle_slug: {lifecycle_slug}\nstatus: refined\n---\n\nBody.\n",
    )


def _review_no_drift() -> str:
    return (
        "# Review: my-feature\n\n"
        "## Stage 1: Spec Compliance\n\n"
        "All requirements PASS.\n\n"
        "## Requirements Drift\n"
        "**State**: none\n"
        "**Findings**:\n"
        "- None\n"
        "**Update needed**: None\n\n"
        "## Verdict\n\n"
        '```json\n{"verdict": "APPROVED", "cycle": 1, "issues": [], '
        '"requirements_drift": "none"}\n```\n'
    )


def _review_with_drift(file_path: str) -> str:
    return (
        "# Review: my-feature\n\n"
        "## Stage 1: Spec Compliance\n\n"
        "All requirements PASS.\n\n"
        "## Requirements Drift\n"
        "**State**: detected\n"
        "**Findings**:\n"
        "- A new constraint surfaced during implementation.\n"
        f"**Update needed**: {file_path}\n\n"
        "## Suggested Requirements Update\n"
        f"**File**: {file_path}\n"
        "**Section**: Quality Attributes\n"
        "**Content**:\n"
        "```\n"
        "- A new constraint bullet.\n"
        "```\n\n"
        "## Verdict\n\n"
        '```json\n{"verdict": "APPROVED", "cycle": 1, "issues": [], '
        '"requirements_drift": "detected"}\n```\n'
    )


_APPROVAL_EVENTS = (
    '{"event": "lifecycle_started", "feature": "my-feature"}\n'
    '{"event": "phase_transition", "from": "research", "to": "specify"}\n'
    '{"event": "phase_transition", "from": "specify", "to": "plan"}\n'
)

_CANCEL_EVENTS = (
    '{"event": "lifecycle_started", "feature": "my-feature"}\n'
    '{"event": "phase_transition", "from": "specify", "to": "plan"}\n'
    '{"event": "lifecycle_cancelled", "feature": "my-feature"}\n'
)

_COMPLETE_EVENTS = (
    '{"event": "lifecycle_started", "feature": "my-feature"}\n'
    '{"event": "phase_transition", "from": "review", "to": "complete"}\n'
)


def _write_complete_artifacts(root: Path, review_text: str) -> None:
    """Create the untracked complete-phase lifecycle artifact set (all new)."""
    _write(root, f"{LC}/research.md", "research\n")
    _write(root, f"{LC}/spec.md", "spec\n")
    _write(root, f"{LC}/plan.md", "plan\n")
    _write(root, f"{LC}/review.md", review_text)
    _write(root, f"{LC}/index.md", "lifecycle index\n")
    _write(root, f"{LC}/events.log", _COMPLETE_EVENTS)


# ---------------------------------------------------------------------------
# Req 9 + 11 + 13 — complete full set, backlog write-back, negative controls
# ---------------------------------------------------------------------------


def test_complete_full_set_with_negative_and_no_sweep_controls(tmp_path: Path) -> None:
    root = tmp_path
    _new_repo(root)

    # Baseline tracked files (committed clean) that will become the dirty
    # negative controls. The dropped `git add -u <dir>` sweep would have
    # captured each of these; the explicit-enumerate discipline must not.
    _write(root, "README.md", "base\n")
    _write(root, f"{LC}/residue.md", "tracked residue v1\n")  # lifecycle/ control
    _write(root, "cortex/requirements/project.md", "project v1\n")  # requirements/ control
    _write(root, "cortex/backlog/OTHER.md", "other ticket v1\n")  # bug-2 backlog control
    _commit_all(root, "Initial commit")

    # Dirty the three tracked controls (so `-u` WOULD catch them).
    _write(root, f"{LC}/residue.md", "tracked residue v2 DIRTY\n")
    _write(root, "cortex/requirements/project.md", "project v2 DIRTY\n")
    _write(root, "cortex/backlog/OTHER.md", "other ticket v2 DIRTY\n")

    # Untracked-new artifacts + resolvable backlog write-back set.
    _write_complete_artifacts(root, _review_no_drift())  # no drift section
    _write_ticket(root)
    _write(root, "cortex/backlog/index.md", "backlog index\n")

    result = stage("complete", SLUG, root)

    expected = sorted(LIFECYCLE_COMPLETE + [TICKET_REL, "cortex/backlog/index.md"])
    assert _staged(root) == expected
    assert result["staged_paths"] == expected
    assert result["signal"] == "staged"

    # Sanity: the controls are genuinely dirty (the `-u` sweep would catch them).
    dirty = _unstaged(root)
    for control in (
        f"{LC}/residue.md",
        "cortex/requirements/project.md",
        "cortex/backlog/OTHER.md",
    ):
        assert control in dirty, f"{control} must be a dirty tracked control"
        # ...yet none are staged (no directory glob, no -u sweep).
        assert control not in expected
        assert control not in _staged(root)

    # Req 9 (without-drift half): the requirements file is NOT swept when
    # review.md carries no `## Suggested Requirements Update` section.
    assert "cortex/requirements/project.md" not in _staged(root)


# ---------------------------------------------------------------------------
# Req 9 + 13 — complete with a review-drift File path staged by exact path
# ---------------------------------------------------------------------------


def test_complete_stages_review_drift_requirements_file(tmp_path: Path) -> None:
    root = tmp_path
    _new_repo(root)

    _write(root, "README.md", "base\n")
    _write(root, "cortex/requirements/project.md", "project v1\n")
    _commit_all(root, "Initial commit")

    # Dirty the requirements file so the explicit drift-path add stages a change.
    _write(root, "cortex/requirements/project.md", "project v2 DIRTY\n")

    _write_complete_artifacts(
        root, _review_with_drift("cortex/requirements/project.md")
    )
    _write_ticket(root)
    _write(root, "cortex/backlog/index.md", "backlog index\n")

    result = stage("complete", SLUG, root)

    expected = sorted(
        LIFECYCLE_COMPLETE
        + [
            TICKET_REL,
            "cortex/backlog/index.md",
            "cortex/requirements/project.md",
        ]
    )
    assert _staged(root) == expected
    assert result["staged_paths"] == expected
    # The drift File path is staged ONLY because review.md names it.
    assert "cortex/requirements/project.md" in _staged(root)


# ---------------------------------------------------------------------------
# Req 9 + 10 — refine approval stages spec.md
# ---------------------------------------------------------------------------


def test_refine_approval_stages_spec(tmp_path: Path) -> None:
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _commit_all(root, "Initial commit")

    _write(root, f"{LC}/research.md", "research\n")
    _write(root, f"{LC}/spec.md", "spec\n")
    _write(root, f"{LC}/index.md", "lifecycle index\n")
    _write(root, f"{LC}/events.log", _APPROVAL_EVENTS)
    _write_ticket(root)

    result = stage("refine", SLUG, root)

    expected = sorted(
        [
            f"{LC}/research.md",
            f"{LC}/spec.md",
            f"{LC}/index.md",
            f"{LC}/events.log",
            TICKET_REL,
        ]
    )
    assert _staged(root) == expected
    assert result["staged_paths"] == expected
    assert result["signal"] == "staged"
    assert f"{LC}/spec.md" in _staged(root)


# ---------------------------------------------------------------------------
# Req 9 + 10 — refine cancel omits spec.md (even though it is present on disk)
# ---------------------------------------------------------------------------


def test_refine_cancel_omits_spec_even_when_present(tmp_path: Path) -> None:
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _commit_all(root, "Initial commit")

    _write(root, f"{LC}/research.md", "research\n")
    _write(root, f"{LC}/spec.md", "spec PRESENT but must NOT stage\n")  # on disk!
    _write(root, f"{LC}/index.md", "lifecycle index\n")
    _write(root, f"{LC}/events.log", _CANCEL_EVENTS)
    _write_ticket(root)

    result = stage("refine", SLUG, root)

    expected = sorted(
        [
            f"{LC}/research.md",
            f"{LC}/index.md",
            f"{LC}/events.log",
            TICKET_REL,
        ]
    )
    assert _staged(root) == expected
    assert result["staged_paths"] == expected
    # Discriminating: spec.md exists on disk but the cancel sub-mode omits it.
    assert (root / LC / "spec.md").exists()
    assert f"{LC}/spec.md" not in _staged(root)


# ---------------------------------------------------------------------------
# Req 11 — resolver exit-3: no backlog file staged, verb still exits 0
# ---------------------------------------------------------------------------


def test_complete_exit3_stages_no_backlog_and_succeeds(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path
    _new_repo(root)

    _write(root, "README.md", "base\n")
    # A backlog dir that exists with an UNRELATED ticket + a clean index.md.
    # The resolver returns not_found for SLUG (exit-3 emergent), and the clean
    # index.md is unmodified so its add no-ops — neither backlog path stages.
    _write_ticket(
        root,
        filename="900-unrelated-other-thing.md",
        lifecycle_slug="unrelated-other-thing",
        title="Unrelated other thing",
    )
    _write(root, "cortex/backlog/index.md", "backlog index\n")
    _commit_all(root, "Initial commit")  # backlog committed CLEAN

    # Only the lifecycle artifacts are dirty/new.
    _write_complete_artifacts(root, _review_no_drift())

    # Drive the CLI main() to assert exit 0 + JSON shape under cwd-root resolution.
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(root)
    rc = main(["--phase", "complete", "--feature", SLUG])
    out = capsys.readouterr().out

    assert rc == 0  # verb still succeeds on the exit-3 emergent path
    parsed = json.loads(out)

    assert _staged(root) == LIFECYCLE_COMPLETE
    assert parsed["staged_paths"] == LIFECYCLE_COMPLETE
    assert parsed["signal"] == "staged"
    # No backlog path staged: not the resolver's no-match ticket, not index.md.
    assert not any(p.startswith("cortex/backlog/") for p in _staged(root))


# ---------------------------------------------------------------------------
# Req 12 — signal: nothing_staged on a no-op re-run vs staged on a real stage
# ---------------------------------------------------------------------------


def test_signal_staged_then_nothing_staged_on_noop_rerun(tmp_path: Path) -> None:
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _commit_all(root, "Initial commit")

    _write_complete_artifacts(root, _review_no_drift())
    _write_ticket(root)
    _write(root, "cortex/backlog/index.md", "backlog index\n")

    # First stage: real changes → signal "staged", quiet exits 1.
    first = stage("complete", SLUG, root)
    assert first["signal"] == "staged"
    assert first["staged_paths"]  # non-empty
    assert _diff_cached_quiet_exit(root) == 1

    # Commit everything so the index matches HEAD.
    _commit_all(root, "Stage and commit finalization artifacts")
    assert _diff_cached_quiet_exit(root) == 0

    # Re-run: same files unmodified → git add no-ops → signal "nothing_staged".
    second = stage("complete", SLUG, root)
    assert second["signal"] == "nothing_staged"
    assert second["staged_paths"] == []
    assert _diff_cached_quiet_exit(root) == 0


# ---------------------------------------------------------------------------
# CLI contract — main() emits one compact JSON line and exits 0
# ---------------------------------------------------------------------------


def test_cli_main_emits_compact_json_line(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _commit_all(root, "Initial commit")

    _write_complete_artifacts(root, _review_no_drift())
    _write_ticket(root)
    _write(root, "cortex/backlog/index.md", "backlog index\n")

    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(root)
    rc = main(["--phase", "complete", "--feature", SLUG])
    out = capsys.readouterr().out

    assert rc == 0
    assert out.endswith("\n")
    assert out.count("\n") == 1  # single line
    # Compact separators (no whitespace after , or :).
    assert ", " not in out and ": " not in out
    parsed = json.loads(out)
    assert set(parsed) == {"signal", "staged_paths"}
    assert parsed["signal"] == "staged"
