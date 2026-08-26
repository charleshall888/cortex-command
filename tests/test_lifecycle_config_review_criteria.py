"""#504 — a config section that arms nothing must say so, and must not ship.

Measured in wild-light during #479 (2026-08-06): `grep -rn "Review Criteria"`
across the whole installed skill package hit only the scaffolded template
asset. Nothing loads the section, and only the frontmatter `test-command` is
executed at Review — so a bullet added there, which is the natural place to put
a new review requirement, is inert prose that reads as authoritative.

Two halves: existing repos that already filled the section get a warning
(nothing is silently dropped), and new repos never get handed the trap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command import lifecycle_config

REPO_ROOT = Path(__file__).resolve().parent.parent

_SCAFFOLD_ASSETS = (
    "cortex_command/init/templates/cortex/lifecycle.config.md",
    "skills/build/assets/lifecycle.config.md",
)


@pytest.fixture(autouse=True)
def _reset_warn_dedup():
    """The warn set is process-global and deduped; clear it per test."""
    lifecycle_config._WARNED_HEADINGS.clear()
    yield
    lifecycle_config._WARNED_HEADINGS.clear()


def _config(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "cortex"
    root.mkdir(parents=True, exist_ok=True)
    (root / "lifecycle.config.md").write_text(
        "---\ncommit-artifacts: true\n---\n\n" + body, encoding="utf-8"
    )
    return tmp_path


def test_dormant_heading_is_announced(tmp_path, capsys) -> None:
    root = _config(tmp_path, "## Review Criteria\n\n- do the thing\n")
    lifecycle_config.read_commit_artifacts(root)
    err = capsys.readouterr().err
    assert "Review Criteria" in err
    assert "not read by any consumer" in err


def test_unknown_heading_is_announced(tmp_path, capsys) -> None:
    root = _config(tmp_path, "## Deploy Gates\n\n- do the thing\n")
    lifecycle_config.read_commit_artifacts(root)
    assert "Deploy Gates" in capsys.readouterr().err


def test_warning_does_not_change_the_parsed_value(tmp_path) -> None:
    """Fail-open by contract: the audit surface is not a validator."""
    root = _config(tmp_path, "## Review Criteria\n")
    assert lifecycle_config.read_commit_artifacts(root) is True


def test_a_body_with_no_sections_is_silent(tmp_path, capsys) -> None:
    root = _config(tmp_path, "# Lifecycle Configuration\n\nSome prose.\n")
    lifecycle_config.read_commit_artifacts(root)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("rel", _SCAFFOLD_ASSETS)
def test_scaffold_no_longer_ships_the_inert_section(rel: str) -> None:
    """Absence assertion: re-adding it hands every new repo the same trap."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "Review Criteria" not in text
