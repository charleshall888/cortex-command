"""Behavior tests for ``cortex-lifecycle-apply-drift``.

The verb turns Review's requirements-drift step from append-only into an edit.
These pin the edit contract: a matched ``Replace`` is replaced in place, an
unmatched one rejects without writing, and an append happens only on
``Replace: None``.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.lifecycle.apply_drift import apply_drift, parse_entries

DOC = """# Requirements: demo

## Functional Requirements

### Sync

- **Retry**: the client retries three times.
- **Timeout**: a call times out after 30 seconds.

## Edge Cases

- **Offline**: the client queues writes.
"""


def _setup(tmp_path: Path, update: str, doc: str = DOC) -> Path:
    req = tmp_path / "cortex" / "requirements"
    req.mkdir(parents=True)
    (req / "demo.md").write_text(doc, encoding="utf-8")
    life = tmp_path / "cortex" / "lifecycle" / "feat"
    life.mkdir(parents=True)
    (life / "review.md").write_text(
        "# Review\n\n## Requirements Drift\n\n- **State**: detected\n\n"
        "## Suggested Requirements Update\n\n" + update + "\n\n```json\n{}\n```\n",
        encoding="utf-8",
    )
    return req / "demo.md"


def _entry(replace: str, with_: str, section: str = "Sync", file: str = "cortex/requirements/demo.md") -> str:
    return (
        f"- **File**: {file}\n- **Section**: {section}\n"
        f"- **Replace**: {replace}\n- **With**: {with_}\n"
    )


def test_replace_edits_in_place_and_does_not_grow_the_section(tmp_path):
    doc = _setup(tmp_path, _entry("the client retries three times.", "the client retries five times."))
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "applied"
    text = doc.read_text()
    assert "retries five times" in text and "retries three times" not in text
    assert len(text.splitlines()) == len(DOC.splitlines())


def test_replace_none_appends_at_the_end_of_the_named_section(tmp_path):
    doc = _setup(tmp_path, _entry("None", "- **Backoff**: retries wait one second."))
    assert apply_drift("feat", tmp_path)["state"] == "applied"
    lines = doc.read_text().splitlines()
    assert lines[lines.index("- **Timeout**: a call times out after 30 seconds.") + 1] == (
        "- **Backoff**: retries wait one second."
    )


def test_with_none_deletes(tmp_path):
    doc = _setup(tmp_path, _entry("- **Timeout**: a call times out after 30 seconds.\n", "None"))
    assert apply_drift("feat", tmp_path)["state"] == "applied"
    assert "Timeout" not in doc.read_text()


def test_unmatched_replace_rejects_and_never_falls_back_to_append(tmp_path):
    doc = _setup(tmp_path, _entry("the client retries twice.", "the client retries five times."))
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "rejected"
    assert "Replace text is not in that section" in result["message"]
    assert doc.read_text() == DOC


def test_replace_is_scoped_to_the_named_section(tmp_path):
    doc = _setup(tmp_path, _entry("the client queues writes.", "the client drops writes."))
    assert apply_drift("feat", tmp_path)["state"] == "rejected"
    assert doc.read_text() == DOC


def test_ambiguous_replace_rejects(tmp_path):
    doc = _setup(tmp_path, _entry("times", "tries", section="Functional Requirements"))
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "rejected" and "matches 2 places" in result["message"]
    assert doc.read_text() == DOC


def test_rerun_reports_already_applied_and_changes_nothing(tmp_path):
    doc = _setup(tmp_path, _entry("the client retries three times.", "the client retries five times."))
    apply_drift("feat", tmp_path)
    once = doc.read_text()
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "applied"
    assert result["entries"][0]["result"] == "already-applied"
    assert doc.read_text() == once


def test_history_in_with_rejects(tmp_path):
    doc = _setup(
        tmp_path,
        _entry("the client retries three times.", "the client retries five times (amended 2026-09-14)."),
    )
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "rejected" and "history" in result["message"]
    assert doc.read_text() == DOC


def test_one_bad_entry_blocks_every_write(tmp_path):
    update = _entry("the client retries three times.", "the client retries five times.") + "\n" + _entry(
        "no such text", "x", section="Edge Cases"
    )
    doc = _setup(tmp_path, update)
    assert apply_drift("feat", tmp_path)["state"] == "rejected"
    assert doc.read_text() == DOC


def test_file_outside_requirements_rejects(tmp_path):
    _setup(tmp_path, _entry("None", "x", file="CLAUDE.md"))
    (tmp_path / "CLAUDE.md").write_text("# x\n\n## Sync\n")
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "rejected"
    assert (tmp_path / "CLAUDE.md").read_text() == "# x\n\n## Sync\n"


def test_missing_section_reports_no_section(tmp_path):
    _setup(tmp_path, "")
    review = tmp_path / "cortex" / "lifecycle" / "feat" / "review.md"
    review.write_text("# Review\n\n## Requirements Drift\n- **State**: detected\n")
    assert apply_drift("feat", tmp_path)["state"] == "no-section"


def test_legacy_content_entry_rejects_with_the_missing_fields_named(tmp_path):
    doc = _setup(
        tmp_path,
        "- **File**: cortex/requirements/demo.md\n- **Section**: Sync\n- **Content**: - a new line\n",
    )
    result = apply_drift("feat", tmp_path)
    assert result["state"] == "rejected" and "Replace" in result["message"]
    assert doc.read_text() == DOC


def test_multiline_fenced_values_parse():
    text = (
        "## Suggested Requirements Update\n\n"
        "- **File**: cortex/requirements/demo.md\n"
        "- **Section**: `## Sync`\n"
        "- **Replace**:\n```\nline one\nline two\n```\n"
        "- **With**: `single`\n"
    )
    (entry,) = parse_entries(text)
    assert entry["Replace"] == "line one\nline two"
    assert entry["With"] == "`single`"
