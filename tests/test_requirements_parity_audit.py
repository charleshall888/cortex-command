"""Fixture-based tests for ``bin/cortex-requirements-parity-audit`` (R9).

Builds a synthetic isolated git repo containing:

  - A pre-#013 archived review.md (mtime + git first-commit before
    2026-04-03). Must be silently skipped from the audit, regardless of
    whether it has a `requirements_drift: detected` block.
  - A post-#013 archived review.md flagging detected drift with a
    Suggested Requirements Update citing `requirements/applied-area.md`,
    where the target requirements doc has a git commit dated AFTER the
    review's first-commit timestamp. Must be counted as ``applied``.
  - A post-#013 active review.md flagging detected drift with a
    Suggested Requirements Update citing `requirements/missing-area.md`,
    where the target requirements doc has NO commit after the review's
    first-commit timestamp (or no commits at all). Must surface in
    ``not_applied``.
  - A post-#013 review.md with `requirements_drift: none` (clean review).
    Audited, never enters applied/not_applied.

Asserts:

  - The script exits 0 against the fixture tree.
  - The JSON output schema matches the documented shape:
      {"audited": int, "applied": int, "not_applied": list[dict]}.
  - Each ``not_applied`` entry has the three required keys
    (``review_path``, ``target``, ``review_date``).
  - At least one ``applied`` count is recorded.
  - At least one ``not_applied`` entry is recorded.
  - The pre-#013 fixture is silently skipped (it does NOT appear in
    ``not_applied`` even though its body has the detected-drift shape).

Design notes:

  - The fixture uses ``git`` to set commit author dates explicitly via
    ``GIT_AUTHOR_DATE`` / ``GIT_COMMITTER_DATE``, so the audit's
    git-first-commit-timestamp logic is exercised end-to-end.
  - The script is invoked via subprocess with ``--root <fixture>`` so the
    test does not depend on cwd and runs hermetically.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-requirements-parity-audit"


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str, env_extra: dict[str, str] | None = None) -> None:
    """Run a git command inside ``repo``, raising on failure."""
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    if env_extra:
        env.update(env_extra)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _commit_file(
    repo: Path,
    rel_path: str,
    content: str,
    author_date: str,
) -> None:
    """Write a file and commit it with a fixed author/committer date."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _run_git(repo, "add", "--", rel_path)
    _run_git(
        repo,
        "commit",
        "-m",
        f"add {rel_path}",
        env_extra={
            "GIT_AUTHOR_DATE": author_date,
            "GIT_COMMITTER_DATE": author_date,
        },
    )


def _make_review_body(state: str, target_doc: str | None) -> str:
    """Render a review.md body with the canonical drift section shapes.

    ``state`` is one of ``"detected"`` or ``"none"``. When state is
    ``"detected"`` AND ``target_doc`` is non-None, a ``## Suggested
    Requirements Update`` section is included citing that doc.
    """
    body = [
        "# Review: fixture",
        "",
        "## Stage 1: Spec Compliance",
        "",
        "### Requirement R1: example",
        "- **Verdict**: PASS",
        "",
        "## Requirements Drift",
        "",
        f"**State**: {state}",
        "",
    ]
    if state == "detected" and target_doc:
        body.extend(
            [
                "## Suggested Requirements Update",
                f"**File**: requirements/{target_doc}",
                '**Section**: "## Some Section"',
                "**Content**:",
                "```",
                "- new bullet",
                "```",
                "",
            ]
        )
    body.extend(
        [
            "## Verdict",
            "```json",
            "{\"verdict\": \"APPROVED\", \"cycle\": 1, \"issues\": [],"
            f' "requirements_drift": "{state}"' + "}",
            "```",
            "",
        ]
    )
    return "\n".join(body)


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """Build a synthetic repo exercising every code path in the audit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    # Disable any user-level commit hooks the host system might inject
    # (e.g. cortex's commit-message validator). Fixture commits use short
    # non-canonical messages on purpose.
    _run_git(repo, "config", "core.hooksPath", "/dev/null")
    # Disable GPG signing — host gitconfig may set commit.gpgsign=true, and
    # the sandbox blocks access to ~/.gnupg, breaking signed commits.
    _run_git(repo, "config", "commit.gpgsign", "false")
    _run_git(repo, "config", "tag.gpgsign", "false")

    # Seed an unrelated file so HEAD exists before adding fixtures.
    _commit_file(
        repo,
        "README.md",
        "fixture\n",
        author_date="2026-01-01T00:00:00Z",
    )

    # --- Case 1: pre-#013 archived review with detected-drift shape ---
    # First-commit date is 2026-03-01 (before the 2026-04-03 cutoff). Even
    # though the body has the detected-drift + suggestion shape, the audit
    # must silently skip it.
    pre013_body = _make_review_body("detected", "pre-cutoff.md")
    _commit_file(
        repo,
        "cortex/lifecycle/archive/pre013-feature/review.md",
        pre013_body,
        author_date="2026-03-01T00:00:00Z",
    )
    # And create a matching requirements doc (so we are testing the date
    # gate, not the missing-target path).
    _commit_file(
        repo,
        "cortex/requirements/pre-cutoff.md",
        "# Pre-cutoff area\n",
        author_date="2026-03-01T00:00:00Z",
    )

    # --- Case 2: post-#013 archived review, target applied AFTER review ---
    # Review committed 2026-04-15. Requirements doc first committed
    # 2026-04-01 (so it pre-exists) BUT amended 2026-05-01 (after the
    # review) — that post-review commit makes it "applied".
    applied_body = _make_review_body("detected", "applied-area.md")
    _commit_file(
        repo,
        "cortex/requirements/applied-area.md",
        "# Applied area v1\n",
        author_date="2026-04-01T00:00:00Z",
    )
    _commit_file(
        repo,
        "cortex/lifecycle/archive/applied-feature/review.md",
        applied_body,
        author_date="2026-04-15T00:00:00Z",
    )
    # Post-review commit that materializes the suggestion.
    target_applied = repo / "cortex/requirements/applied-area.md"
    target_applied.write_text("# Applied area v2 — bullet added\n", encoding="utf-8")
    _run_git(repo, "add", "--", "cortex/requirements/applied-area.md")
    _run_git(
        repo,
        "commit",
        "-m",
        "apply drift suggestion",
        env_extra={
            "GIT_AUTHOR_DATE": "2026-05-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-05-01T00:00:00Z",
        },
    )

    # --- Case 3: post-#013 active review, target NEVER touched after review ---
    # Review committed 2026-04-20. Requirements doc has only a pre-review
    # commit (2026-04-01) — must surface as not_applied.
    not_applied_body = _make_review_body("detected", "missing-area.md")
    _commit_file(
        repo,
        "cortex/requirements/missing-area.md",
        "# Missing area v1\n",
        author_date="2026-04-01T00:00:00Z",
    )
    _commit_file(
        repo,
        "cortex/lifecycle/not-applied-feature/review.md",
        not_applied_body,
        author_date="2026-04-20T00:00:00Z",
    )

    # --- Case 4: post-#013 review with state=none (clean) ---
    # Should be audited but not enter applied/not_applied.
    clean_body = _make_review_body("none", None)
    _commit_file(
        repo,
        "cortex/lifecycle/clean-feature/review.md",
        clean_body,
        author_date="2026-04-25T00:00:00Z",
    )

    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _invoke_audit(repo: Path) -> dict:
    """Invoke the audit script against ``repo`` and return the parsed JSON."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"audit exited {result.returncode}; stderr:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def test_help_flag_exits_zero():
    """`--help` is a contract-level smoke test that R9 acceptance enforces."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "requirements-parity-audit" in result.stdout


def test_output_schema_matches_contract(fixture_repo: Path):
    """The JSON envelope has the three documented top-level keys with the right types."""
    report = _invoke_audit(fixture_repo)
    assert isinstance(report, dict)
    assert set(report.keys()) == {"audited", "applied", "not_applied"}
    assert isinstance(report["audited"], int)
    assert isinstance(report["applied"], int)
    assert isinstance(report["not_applied"], list)


def test_pre013_review_silently_skipped(fixture_repo: Path):
    """A review.md authored before 2026-04-03 must not appear in the audit."""
    report = _invoke_audit(fixture_repo)
    pre013_path = "cortex/lifecycle/archive/pre013-feature/review.md"
    paths = [entry["review_path"] for entry in report["not_applied"]]
    assert pre013_path not in paths


def test_applied_count_records_post_review_commit(fixture_repo: Path):
    """A drift suggestion materialized by a post-review commit is counted as applied."""
    report = _invoke_audit(fixture_repo)
    assert report["applied"] >= 1
    not_applied_paths = [entry["review_path"] for entry in report["not_applied"]]
    assert "cortex/lifecycle/archive/applied-feature/review.md" not in not_applied_paths


def test_not_applied_lists_missing_application(fixture_repo: Path):
    """A drift suggestion with no post-review commit on the target surfaces in not_applied."""
    report = _invoke_audit(fixture_repo)
    paths = [entry["review_path"] for entry in report["not_applied"]]
    assert "cortex/lifecycle/not-applied-feature/review.md" in paths


def test_not_applied_entry_schema(fixture_repo: Path):
    """Each not_applied entry has review_path, target, and review_date (ISO-8601)."""
    report = _invoke_audit(fixture_repo)
    assert len(report["not_applied"]) >= 1
    entry = next(
        e
        for e in report["not_applied"]
        if e["review_path"] == "cortex/lifecycle/not-applied-feature/review.md"
    )
    assert set(entry.keys()) == {"review_path", "target", "review_date"}
    assert entry["target"] == "cortex/requirements/missing-area.md"
    # review_date is ISO-8601 with a timezone — must parse as such.
    import datetime as _dt

    parsed = _dt.datetime.fromisoformat(entry["review_date"])
    assert parsed.tzinfo is not None
    # And the parsed timestamp matches what we committed.
    assert parsed.year == 2026 and parsed.month == 4 and parsed.day == 20


def test_audited_counts_all_in_scope(fixture_repo: Path):
    """audited counts in-scope reviews regardless of drift state.

    Three post-#013 reviews exist (applied-feature, not-applied-feature,
    clean-feature). The pre-#013 archived review is silently dropped, so
    audited == 3.
    """
    report = _invoke_audit(fixture_repo)
    assert report["audited"] == 3
