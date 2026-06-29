"""Tests for the `cortex-refine resume-point` read-only subcommand.

Drives all four artifact states plus the edge cases through the production
entry point (`cortex_command.refine.main`) in-process — same idiom as
`tests/test_refine_reconcile_clarify.py`, so the verb is exercised against the
working-tree source without a wheel reinstall.

The verb classifies the refine resume state from filesystem artifact-stat:
``spec ∧ research`` → ``complete``; ``spec ∧ ¬research`` → ``research``;
``research ∧ ¬spec`` → ``spec``; else → ``clarify``. Existence is ``is_file()``
(a directory named ``spec.md``/``research.md`` does not count; an empty
``spec.md`` does). Exit 0 for every state; argparse exit 2 on a missing flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.refine import main


def _lifecycle_dir(tmp_path: Path, slug: str) -> Path:
    d = tmp_path / "cortex" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(
    capsys: pytest.CaptureFixture[str], slug: str
) -> tuple[int, dict]:
    rc = main(["resume-point", "--lifecycle-slug", slug])
    out = capsys.readouterr().out.strip()
    return rc, json.loads(out)


# ---------------------------------------------------------------------------
# Four artifact states
# ---------------------------------------------------------------------------


def test_spec_and_research_present_resolves_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    d = _lifecycle_dir(tmp_path, "feat")
    (d / "spec.md").write_text("spec", encoding="utf-8")
    (d / "research.md").write_text("research", encoding="utf-8")

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    assert obj == {"resume": "complete", "spec_exists": True, "research_exists": True}


def test_spec_only_resolves_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    d = _lifecycle_dir(tmp_path, "feat")
    (d / "spec.md").write_text("spec", encoding="utf-8")

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    assert obj == {"resume": "research", "spec_exists": True, "research_exists": False}


def test_research_only_resolves_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    d = _lifecycle_dir(tmp_path, "feat")
    (d / "research.md").write_text("research", encoding="utf-8")

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    assert obj == {"resume": "spec", "spec_exists": False, "research_exists": True}


def test_no_artifacts_resolves_clarify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _lifecycle_dir(tmp_path, "feat")  # dir exists but is empty

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    assert obj == {"resume": "clarify", "spec_exists": False, "research_exists": False}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_missing_lifecycle_dir_resolves_clarify_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    # No cortex/lifecycle/feat dir created at all.
    rc, obj = _run(capsys, "feat")
    assert rc == 0
    assert obj == {"resume": "clarify", "spec_exists": False, "research_exists": False}


def test_empty_spec_file_counts_as_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    d = _lifecycle_dir(tmp_path, "feat")
    (d / "spec.md").write_text("", encoding="utf-8")  # empty but present

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    # Empty spec.md still counts (is_file() is True); non-empty is a separate gate.
    assert obj["spec_exists"] is True
    assert obj["resume"] == "research"


def test_directory_named_research_md_does_not_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    d = _lifecycle_dir(tmp_path, "feat")
    (d / "spec.md").write_text("spec", encoding="utf-8")
    (d / "research.md").mkdir()  # a DIRECTORY named research.md

    rc, obj = _run(capsys, "feat")
    assert rc == 0
    # is_file() is False for a directory, so research does not count.
    assert obj["research_exists"] is False
    assert obj["resume"] == "research"


def test_missing_lifecycle_slug_flag_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(["resume-point"])
    assert exc_info.value.code == 2
