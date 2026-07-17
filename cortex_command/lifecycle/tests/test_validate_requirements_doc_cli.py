"""Tests for cortex-validate-requirements-doc — requirements-write's
mechanical acceptance gate (required H2 sections; project-scope ## Optional
token budget).
"""

from __future__ import annotations

import json

import pytest

from cortex_command.lifecycle import validate_requirements_doc_cli as vd

_VALID_PROJECT_DOC = """# Requirements: x

> Last gathered: 2026-04-01

## Overview

x

## Philosophy of Work

- a

## Architectural Constraints

- b

## Quality Attributes

- c

## Project Boundaries

### In Scope
- d

### Out of Scope
- e

### Deferred
- f

## Conditional Loading

- trig → cortex/requirements/area.md

## Global Context

- cortex/requirements/glossary.md

## Optional

- short note
"""

_VALID_AREA_DOC = """# Requirements: area

> Last gathered: 2026-04-01

**Parent doc**: [requirements/project.md](project.md)

## Overview

x

## Functional Requirements

### Capability

- **Description**: d

## Non-Functional Requirements

- a

## Architectural Constraints

- b

## Dependencies

- c

## Edge Cases

- **Condition**: behavior

## Open Questions

- None
"""


def test_pass_project_doc(tmp_path) -> None:
    p = tmp_path / "project.md"
    p.write_text(_VALID_PROJECT_DOC, encoding="utf-8")
    r = vd.validate_requirements_doc(p, "project")
    assert r["state"] == "pass"
    by_name = {c["name"]: c for c in r["checks"]}
    assert by_name["required-sections"]["pass"] is True
    assert by_name["required-sections"]["missing"] == []
    assert by_name["optional-token-budget"]["applicable"] is True
    assert by_name["optional-token-budget"]["pass"] is True


def test_pass_area_doc(tmp_path) -> None:
    p = tmp_path / "area.md"
    p.write_text(_VALID_AREA_DOC, encoding="utf-8")
    r = vd.validate_requirements_doc(p, "area")
    assert r["state"] == "pass"
    by_name = {c["name"]: c for c in r["checks"]}
    assert by_name["required-sections"]["missing"] == []
    assert by_name["optional-token-budget"]["applicable"] is False
    assert by_name["optional-token-budget"]["pass"] is True


def test_fail_missing_section(tmp_path) -> None:
    text = _VALID_PROJECT_DOC.replace("## Quality Attributes\n\n- c\n\n", "")
    p = tmp_path / "project.md"
    p.write_text(text, encoding="utf-8")
    r = vd.validate_requirements_doc(p, "project")
    assert r["state"] == "fail"
    by_name = {c["name"]: c for c in r["checks"]}
    assert by_name["required-sections"]["pass"] is False
    assert "Quality Attributes" in by_name["required-sections"]["missing"]


def test_fail_optional_over_budget(tmp_path) -> None:
    # Body far above the 1,200-token budget (4 chars/token → ~2,000 tokens).
    over_budget_text = "a " * 4000
    text = _VALID_PROJECT_DOC.replace(
        "## Optional\n\n- short note\n", f"## Optional\n\n{over_budget_text}\n"
    )
    p = tmp_path / "project.md"
    p.write_text(text, encoding="utf-8")
    r = vd.validate_requirements_doc(p, "project")
    assert r["state"] == "fail"
    by_name = {c["name"]: c for c in r["checks"]}
    assert by_name["optional-token-budget"]["pass"] is False
    assert by_name["optional-token-budget"]["token_count"] > vd.OPTIONAL_TOKEN_BUDGET


def test_pass_optional_at_exact_budget(tmp_path) -> None:
    # The estimate is a deterministic 4-chars/token count, so land the extracted
    # section exactly on the budget via the real extraction+count pipeline. The
    # count rises by 1 every 4 chars (never overshoots), so nudging the body
    # length from the ~budget*4 starting point converges in a couple of steps.
    def _measure(body: str):
        text = _VALID_PROJECT_DOC.replace(
            "## Optional\n\n- short note\n", f"## Optional\n\n{body}\n"
        )
        section = vd._section_text(text, vd.OPTIONAL_HEADING)
        return vd._estimate_tokens(section), text

    body_len = vd.OPTIONAL_TOKEN_BUDGET * 4
    count, text = _measure("a" * body_len)
    while count > vd.OPTIONAL_TOKEN_BUDGET:
        body_len -= 1
        count, text = _measure("a" * body_len)
    while count < vd.OPTIONAL_TOKEN_BUDGET:
        body_len += 1
        count, text = _measure("a" * body_len)
    assert count == vd.OPTIONAL_TOKEN_BUDGET

    p = tmp_path / "project.md"
    p.write_text(text, encoding="utf-8")
    r = vd.validate_requirements_doc(p, "project")
    by_name = {c["name"]: c for c in r["checks"]}
    assert by_name["optional-token-budget"]["token_count"] == vd.OPTIONAL_TOKEN_BUDGET
    assert by_name["optional-token-budget"]["pass"] is True


def test_file_not_found(tmp_path) -> None:
    r = vd.validate_requirements_doc(tmp_path / "missing.md", "project")
    assert r["state"] == "file-not-found"


def test_unknown_scope_raises_value_error(tmp_path) -> None:
    p = tmp_path / "x.md"
    p.write_text(_VALID_PROJECT_DOC, encoding="utf-8")
    with pytest.raises(ValueError):
        vd.validate_requirements_doc(p, "bogus")


def test_every_state_is_known(tmp_path) -> None:
    seen = set()
    p = tmp_path / "project.md"
    p.write_text(_VALID_PROJECT_DOC, encoding="utf-8")
    seen.add(vd.validate_requirements_doc(p, "project")["state"])  # pass
    seen.add(vd.validate_requirements_doc(tmp_path / "missing.md", "project")["state"])  # file-not-found
    bad = tmp_path / "bad.md"
    bad.write_text("# Requirements: x\n\n## Overview\n", encoding="utf-8")
    seen.add(vd.validate_requirements_doc(bad, "project")["state"])  # fail
    assert seen <= set(vd.KNOWN_STATES)
    assert seen == {"pass", "file-not-found", "fail"}


def test_cli_emits_json(tmp_path, capsys) -> None:
    p = tmp_path / "project.md"
    p.write_text(_VALID_PROJECT_DOC, encoding="utf-8")
    rc = vd.main(["--path", str(p), "--scope", "project"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "pass"


def test_cli_never_raises_and_always_exits_zero(tmp_path, capsys) -> None:
    # Invalid-UTF-8 bytes make ``path.read_text(encoding="utf-8")`` raise
    # inside ``validate_requirements_doc`` — a real internal failure (as
    # opposed to a bad ``--scope``, which argparse's ``choices=`` rejects
    # before ``main``'s body ever runs, per every other verb's CLI-syntax
    # contract).
    p = tmp_path / "project.md"
    p.write_bytes(b"\xff\xfe not valid utf-8 \x00")
    rc = vd.main(["--path", str(p), "--scope", "project"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
