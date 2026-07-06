"""Tests for cortex-append-glossary-term — the requirements-gather glossary
file I/O verb: a read-only probe mode (omit --definition) and a guarded-write
mode (pass --definition) against cortex/requirements/glossary.md's
## Language section.
"""

from __future__ import annotations

import json

import pytest

from cortex_command.common import CortexProjectRootError
from cortex_command.lifecycle import append_glossary_term_cli as gt


def _glossary_path(root):
    return root / "cortex" / "requirements" / "glossary.md"


def test_appended_creates_file_lazily(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    assert not path.exists()

    r = gt.append_glossary_term(
        "phase transition",
        "the named event emitted when a lifecycle phase completes",
        glossary_path=path,
    )
    assert r == {
        "state": "appended",
        "term": "phase transition",
        "definition": "the named event emitted when a lifecycle phase completes",
    }
    text = path.read_text(encoding="utf-8")
    assert "## Language" in text
    assert "- **phase transition**: the named event emitted when a lifecycle phase completes" in text


def test_appended_adds_second_bullet_to_existing_section(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Glossary\n\n## Language\n\n- **kept pause**: a phase-blocking wait\n",
        encoding="utf-8",
    )

    r = gt.append_glossary_term("sentinel", "a marker line", glossary_path=path)
    assert r["state"] == "appended"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines.count("- **kept pause**: a phase-blocking wait") == 1
    assert "- **sentinel**: a marker line" in lines
    # New bullet lands directly after the existing one, inside the section.
    assert lines.index("- **sentinel**: a marker line") == lines.index(
        "- **kept pause**: a phase-blocking wait"
    ) + 1


def test_appends_new_language_section_when_file_exists_without_one(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("# Glossary\n\nSome preamble.\n", encoding="utf-8")

    r = gt.append_glossary_term("term", "def", glossary_path=path)
    assert r["state"] == "appended"
    text = path.read_text(encoding="utf-8")
    assert "Some preamble." in text
    assert "## Language" in text
    assert "- **term**: def" in text


def test_existed_without_replace_leaves_file_untouched(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    path.parent.mkdir(parents=True)
    original = "# Glossary\n\n## Language\n\n- **phase transition**: original def\n"
    path.write_text(original, encoding="utf-8")

    r = gt.append_glossary_term(
        "Phase Transition", "a different candidate def", glossary_path=path
    )
    assert r == {
        "state": "existed",
        "term": "Phase Transition",
        "definition": "original def",
    }
    assert path.read_text(encoding="utf-8") == original


def test_replace_overwrites_existing_definition(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Glossary\n\n## Language\n\n- **phase transition**: original def\n",
        encoding="utf-8",
    )

    r = gt.append_glossary_term(
        "phase transition", "new def", glossary_path=path, replace=True
    )
    assert r == {"state": "replaced", "term": "phase transition", "definition": "new def"}
    text = path.read_text(encoding="utf-8")
    assert "- **phase transition**: new def" in text
    assert "original def" not in text


# ---------------------------------------------------------------------------
# Probe mode (--definition omitted / definition=None): read-only.
# ---------------------------------------------------------------------------


def test_probe_not_found_writes_nothing(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    r = gt.append_glossary_term("phase transition", glossary_path=path)
    assert r == {"state": "not-found", "term": "phase transition"}
    assert not path.exists()


def test_probe_found_returns_existing_definition_without_writing(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    path.parent.mkdir(parents=True)
    original = "# Glossary\n\n## Language\n\n- **phase transition**: original def\n"
    path.write_text(original, encoding="utf-8")

    r = gt.append_glossary_term("Phase Transition", glossary_path=path)
    assert r == {
        "state": "found",
        "term": "Phase Transition",
        "definition": "original def",
    }
    assert path.read_text(encoding="utf-8") == original


def test_probe_then_write_matches_classify_gate_ordering(tmp_path) -> None:
    """The skill's real sequence: probe first, write only after gate passes."""
    path = _glossary_path(tmp_path)

    probe = gt.append_glossary_term("sentinel", glossary_path=path)
    assert probe["state"] == "not-found"
    assert not path.exists(), "probe must never create the file"

    write = gt.append_glossary_term("sentinel", "a marker line", glossary_path=path)
    assert write["state"] == "appended"
    assert path.exists()


def test_cli_probe_mode_omits_definition(tmp_path, capsys) -> None:
    path = _glossary_path(tmp_path)
    rc = gt.main(["--term", "t", "--glossary-path", str(path)])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "not-found"
    assert not path.exists()


def test_project_root_error_returns_state_not_traceback(monkeypatch) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(gt, "_resolve_user_project_root_from_cwd", _raise)
    r = gt.append_glossary_term("t", "d")
    assert r["state"] == "error"
    assert "no cortex/ found" in r["message"]


def test_io_failure_returns_error_state_not_traceback(tmp_path, monkeypatch) -> None:
    path = _glossary_path(tmp_path)

    def _raise(p, content, encoding="utf-8"):
        raise OSError("disk full")

    monkeypatch.setattr(gt, "atomic_write", _raise)
    r = gt.append_glossary_term("t", "d", glossary_path=path)
    assert r["state"] == "error"
    assert "disk full" in r["message"]


def test_every_state_is_known(tmp_path) -> None:
    path = _glossary_path(tmp_path)
    seen = set()
    seen.add(gt.append_glossary_term("t", glossary_path=path)["state"])  # not-found
    seen.add(gt.append_glossary_term("t", "d1", glossary_path=path)["state"])  # appended
    seen.add(gt.append_glossary_term("t", glossary_path=path)["state"])  # found
    seen.add(gt.append_glossary_term("t", "d2", glossary_path=path)["state"])  # existed
    seen.add(
        gt.append_glossary_term("t", "d3", glossary_path=path, replace=True)["state"]
    )  # replaced
    assert seen <= set(gt.KNOWN_STATES)
    assert seen == {"not-found", "appended", "found", "existed", "replaced"}


def test_cli_emits_json(tmp_path, capsys) -> None:
    path = _glossary_path(tmp_path)
    rc = gt.main(
        ["--term", "t", "--definition", "d", "--glossary-path", str(path)]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "appended"
    assert obj["term"] == "t"


def test_cli_replace_flag(tmp_path, capsys) -> None:
    path = _glossary_path(tmp_path)
    gt.main(["--term", "t", "--definition", "d1", "--glossary-path", str(path)])
    capsys.readouterr()
    rc = gt.main(
        [
            "--term", "t",
            "--definition", "d2",
            "--glossary-path", str(path),
            "--replace",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "replaced"
    assert obj["definition"] == "d2"


def test_cli_never_raises_and_always_exits_zero(monkeypatch, capsys) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(gt, "_resolve_user_project_root_from_cwd", _raise)
    rc = gt.main(["--term", "t", "--definition", "d"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
