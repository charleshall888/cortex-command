"""Content tests for ``cortex-lifecycle-review-brief``.

Pins the *content* half of the verb's contract — the pure-builder layer plus
the git-derived baseline rule — against
``cortex/lifecycle/a-rework-re-review-re-reads/spec.md`` requirements 7, 8, 10,
11, 13 and 18. The CLI-layer behaviors (archive, mode selection, fail-open) are
pinned separately in ``test_review_brief_cli.py``.

Every case runs against a **real** temp git repo: the baseline decision and the
brief's commit range are derived from an actual ``git diff``/``git rev-parse``,
so a fixture cannot fake a range the reviewer could not actually read. The
module is imported directly rather than invoked through the ``cortex-*`` name on
PATH, which resolves to the released wheel rather than this worktree.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from cortex_command.lifecycle import review_brief as rb

FEATURE = "fixture-feature"

# A 3-issue prior verdict, per requirements 7 and 18.
ISSUES = [
    "Issue one: the loader ignores the --strict flag on a nested include.",
    "Issue two: the error path swallows OSError without logging the path.",
    "Issue three: no test covers the empty-input case.",
]

_RANGE_RE = re.compile(r"\b([0-9a-f]{40})\.\.HEAD\b")
_SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")


# ---------------------------------------------------------------------------
# Fixture plumbing
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the developer's global/system git config for this test.

    Without this a global ``core.hooksPath`` (or ``diff.relative``, or a signing
    requirement) reaches into the temp repo and the fixture commits behave
    differently on different machines. The module under test shells out to git
    with the inherited environment, so the isolation must be set in the process
    environment rather than passed per-call.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Cortex Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Cortex Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a git repo with a ``cortex/`` root marker; return (root, sha0)."""
    root = tmp_path / "repo"
    (root / "cortex").mkdir(parents=True)
    (root / "cortex" / ".gitkeep").write_text("", encoding="utf-8")
    _git(root.parent, "-c", "init.defaultBranch=main", "init", "--quiet", str(root))
    _git(root, "add", "cortex/.gitkeep")
    _git(root, "commit", "--quiet", "--no-verify", "-m", "Seed the fixture repo")
    return root, _git(root, "rev-parse", "HEAD")


def _commit(root: Path, rel_path: str, body: str, message: str) -> str:
    """Commit *body* at *rel_path*; return the resulting HEAD sha."""
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git(root, "add", "--", rel_path)
    _git(root, "commit", "--quiet", "--no-verify", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _prior_review(cycle: int, *, carried: tuple[str, ...] = ()) -> str:
    """A prior cycle's ``review.md``: rated requirements plus a verdict block.

    Every name in *carried* is rated as carried forward from ``cycle - 1``, the
    input requirement 10's depth bound reads.
    """
    lines = [f"# Review — {FEATURE} · cycle {cycle}", ""]
    for name in carried:
        lines += [
            f"### Requirement: {name}",
            f"PASS — carried forward from cycle {cycle - 1}; holds while the "
            "loader's path list is unchanged",
            "",
        ]
    lines += [
        "### Requirement: Strict flag is honored",
        "FAIL — see the issues below",
        "",
        "## Requirements Drift",
        "",
        "- **State**: `none`",
        "",
        "```json",
        json.dumps(
            {
                "verdict": "CHANGES_REQUESTED",
                "cycle": cycle,
                "issues": list(ISSUES),
                "requirements_drift": {"state": "none"},
            },
            indent=2,
        ),
        "```",
        "",
    ]
    return "\n".join(lines)


def _write_lifecycle(
    root: Path, *, rework_cycles: int, baseline_sha: str, review_text: str
) -> Path:
    """Write an untracked lifecycle whose prior dispatches point at *baseline_sha*.

    The lifecycle files stay untracked so the committed diff the verb takes is
    exactly the one each test sets up.
    """
    feature_dir = root / "cortex" / "lifecycle" / FEATURE
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "review.md").write_text(review_text, encoding="utf-8")

    rows = []
    for n in range(1, rework_cycles + 1):
        rows.append(
            {
                "ts": "2026-08-07T00:00:0%dZ" % n,
                "event": "review_dispatched",
                "feature": FEATURE,
                "cycle": n,
                "mode": "full" if n == 1 else "rework",
                "baseline_sha": baseline_sha,
            }
        )
        rows.append(
            {
                "ts": "2026-08-07T00:01:0%dZ" % n,
                "event": "review_verdict",
                "feature": FEATURE,
                "verdict": "CHANGES_REQUESTED",
                "cycle": n,
            }
        )
    (feature_dir / "events.log").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return feature_dir


def _emit(root: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> str:
    """Run the verb from *root* and return the brief it wrote to stdout."""
    monkeypatch.chdir(root)
    code = rb.main(["--feature", FEATURE])
    out = capsys.readouterr().out
    assert code == 0, f"expected a served brief, got exit {code}"
    return out


def _rework_brief(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    *,
    post_baseline: tuple[str, str] = (
        f"cortex/lifecycle/{FEATURE}/plan.md",
        "- [x] Task 1\n",
    ),
    rework_cycles: int = 1,
    carried: tuple[str, ...] = (),
) -> tuple[str, Path, str]:
    """Build a rework fixture and emit its brief. Returns (brief, root, sha0)."""
    root, sha0 = _init_repo(tmp_path)
    _write_lifecycle(
        root,
        rework_cycles=rework_cycles,
        baseline_sha=sha0,
        review_text=_prior_review(rework_cycles, carried=carried),
    )
    rel, body = post_baseline
    _commit(root, rel, body, "Land the rework")
    return _emit(root, monkeypatch, capsys), root, sha0


def _section(brief: str, title: str) -> str:
    """Return the body of the ``## {title}`` section of *brief*."""
    body: list[str] = []
    capturing = False
    for line in brief.splitlines():
        if line.startswith("## "):
            if capturing:
                break
            capturing = line[3:].strip().lower() == title.lower()
            continue
        if capturing:
            body.append(line)
    text = "\n".join(body).strip()
    assert text, f"brief has no '## {title}' section:\n{brief}"
    return text


# ---------------------------------------------------------------------------
# Requirement 7 — checklist, reading scope, baseline decision
# ---------------------------------------------------------------------------


def test_scoped_brief_names_every_prior_issue(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 7: the brief names each issue from the prior cycle."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    for issue in ISSUES:
        assert brief.count(issue) == 1, f"issue not named exactly once: {issue}"


def test_scoped_brief_states_a_git_diff_expressible_range(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 7 + 13: the range is concrete, is the recorded baseline, and reads."""
    brief, root, sha0 = _rework_brief(tmp_path, monkeypatch, capsys)

    match = _RANGE_RE.search(brief)
    assert match, f"brief states no <sha>..HEAD range:\n{brief}"
    assert match.group(1) == sha0, "range does not open at the recorded dispatch baseline"

    # Expressible means git can actually take it, not merely that it looks like a range.
    proc = subprocess.run(
        ["git", "diff", f"{match.group(1)}..HEAD", "--name-only"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_scoped_brief_states_exactly_one_baseline_decision(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 7: exactly one of "reuse baseline" / "re-run" reaches the brief."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    present = [t for t in (rb.REUSE_BASELINE, rb.RE_RUN) if t in brief]
    assert present == [rb.REUSE_BASELINE], (
        "a lifecycle-only rework must state exactly the reuse token, "
        f"got {present!r}"
    )


def test_source_change_puts_exactly_the_rerun_token_in_the_brief(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 7: the other decision is equally exclusive."""
    brief, _root, _sha0 = _rework_brief(
        tmp_path,
        monkeypatch,
        capsys,
        post_baseline=("cortex_command/widget.py", "VALUE = 1\n"),
    )
    present = [t for t in (rb.REUSE_BASELINE, rb.RE_RUN) if t in brief]
    assert present == [rb.RE_RUN], (
        f"a source-touching rework must state exactly the re-run token, got {present!r}"
    )


# ---------------------------------------------------------------------------
# Requirement 8 — scoping bounds reading, never concluding
# ---------------------------------------------------------------------------


def test_brief_states_scoping_bounds_reading_not_concluding(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 8: the bounding statement is present and says both halves."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    assert re.search(
        r"bounds?\s+(?:your\s+)?reading,?\s+never\s+(?:your\s+)?concluding",
        brief,
        re.IGNORECASE,
    ), f"brief carries no reading-not-concluding bounding statement:\n{brief}"


def test_brief_requires_an_out_of_scope_findings_heading(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 8: the prescribed output shape includes a mandatory findings section."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    assert "## Out-of-Scope Findings" in brief, (
        "brief does not name the heading the review must carry:\n" + brief
    )


def test_nothing_found_must_still_be_stated_affirmatively(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 8: an empty findings section is stated, never omitted."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Out-of-scope findings")
    assert re.search(r"affirmativ", section, re.IGNORECASE), section
    assert re.search(r"\bempty\b", section, re.IGNORECASE), section
    assert re.search(r"never omitted|not be omitted", section, re.IGNORECASE), section


# ---------------------------------------------------------------------------
# Requirement 10 — carry-forward form, condition, and depth bound
# ---------------------------------------------------------------------------


def test_brief_prescribes_the_carry_forward_form_and_its_condition(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 10: carried forward is stated by reference, naming cycle + condition."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Carry-forward")
    assert "carried forward from cycle" in section.lower(), section
    assert re.search(r"\bcondition\b", section, re.IGNORECASE), section


def test_brief_states_the_once_only_bound(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 10: a rating may be carried once; a second time is re-verified."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Carry-forward")
    assert re.search(r"\bonce\b", section, re.IGNORECASE), section
    assert re.search(r"re-verif", section, re.IGNORECASE), section


def test_already_carried_item_is_listed_as_requiring_reverification(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 10: a prior review that already carried an item exhausts the bound."""
    carried = "Loader path list is unchanged"
    brief, _root, _sha0 = _rework_brief(
        tmp_path,
        monkeypatch,
        capsys,
        rework_cycles=2,
        carried=(carried,),
    )
    section = _section(brief, "Carry-forward")
    assert carried in section, (
        "the item the prior review already carried is not listed:\n" + section
    )
    assert re.search(r"re-verif", section, re.IGNORECASE), section


def test_carry_forward_listing_is_absent_when_nothing_was_carried(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """The listing is evidence-driven, not boilerplate the reviewer learns to skip."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Carry-forward")
    assert "exhausted the bound" not in section, section


# ---------------------------------------------------------------------------
# Requirement 18 — one disposition per checklist issue
# ---------------------------------------------------------------------------


def test_brief_demands_one_disposition_per_prior_issue(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 18: three issues, three demanded dispositions, none droppable."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Prior-cycle checklist")

    assert "## Prior-Cycle Checklist" in section, (
        "the brief does not name the section the review must carry:\n" + section
    )
    assert re.search(r"disposition", section, re.IGNORECASE), section

    numbered = re.findall(r"^(\d+)\.\s+(.*\S)\s*$", section, re.MULTILINE)
    assert [n for n, _ in numbered] == ["1", "2", "3"], numbered
    assert [text for _, text in numbered] == ISSUES, numbered

    for value in ("resolved", "not resolved", "partially resolved"):
        assert value in section.lower(), f"disposition vocabulary missing: {value}"


def test_brief_forbids_re_emitting_resolved_issues_as_new_problems(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 18: dedup — a resolved item is not re-reported under new problems."""
    brief, _root, _sha0 = _rework_brief(tmp_path, monkeypatch, capsys)
    section = _section(brief, "Prior-cycle checklist")
    assert re.search(
        r"resolved must not be re-emitted|not be re-emitted", section, re.IGNORECASE
    ), section


# ---------------------------------------------------------------------------
# Requirement 11 — the test-baseline decision rule, over a real repo
# ---------------------------------------------------------------------------


def _decision_for(root: Path, baseline_sha: str) -> str:
    """The decision the verb reaches from a real ``git diff`` against *baseline_sha*."""
    changed = rb._changed_paths(baseline_sha, root)
    assert changed is not None, "the fixture diff could not be taken"
    return rb.decide_test_baseline(changed, FEATURE)


def test_lifecycle_markdown_only_diff_reuses_the_baseline(
    isolated_git, tmp_path
) -> None:
    """Req 11: a diff touching only cortex/lifecycle/{feature}/plan.md → reuse."""
    root, sha0 = _init_repo(tmp_path)
    _commit(root, f"cortex/lifecycle/{FEATURE}/plan.md", "- [x] Task 1\n", "Tick a task")

    assert rb._changed_paths(sha0, root) == [f"cortex/lifecycle/{FEATURE}/plan.md"]
    assert _decision_for(root, sha0) == rb.REUSE_BASELINE


def test_events_log_is_not_exempt_and_forces_a_re_run(isolated_git, tmp_path) -> None:
    """Req 11: events.log is deliberately outside the exemption."""
    root, sha0 = _init_repo(tmp_path)
    _commit(
        root,
        f"cortex/lifecycle/{FEATURE}/events.log",
        '{"event": "review_verdict", "verdict": "CHANGES_REQUESTED"}\n',
        "Log a verdict",
    )

    assert rb._changed_paths(sha0, root) == [f"cortex/lifecycle/{FEATURE}/events.log"]
    assert _decision_for(root, sha0) == rb.RE_RUN


def test_any_source_path_forces_a_re_run(isolated_git, tmp_path) -> None:
    """Req 11: any path outside the exemption → re-run."""
    root, sha0 = _init_repo(tmp_path)
    _commit(root, "cortex_command/widget.py", "VALUE = 1\n", "Add a widget")

    assert rb._changed_paths(sha0, root) == ["cortex_command/widget.py"]
    assert _decision_for(root, sha0) == rb.RE_RUN


# ---------------------------------------------------------------------------
# Requirement 13 — the brief names a resolvable 40-hex commit SHA
# ---------------------------------------------------------------------------


def test_rework_brief_names_a_resolvable_commit_sha(
    isolated_git, tmp_path, monkeypatch, capsys
) -> None:
    """Req 13: the brief matches \\b[0-9a-f]{40}\\b and that SHA resolves."""
    brief, root, sha0 = _rework_brief(tmp_path, monkeypatch, capsys)

    match = _SHA_RE.search(brief)
    assert match, f"brief names no 40-hex SHA:\n{brief}"
    sha = match.group(0)
    assert sha == sha0

    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
