#!/usr/bin/env python3
"""Tests for scripts/validate-callgraph.py.

Guards against the class of bug where one skill programmatically invokes
another skill that carries ``disable-model-invocation: true`` — the flag
blocks the Skill tool entirely, so such callees break their callers.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate-callgraph.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("validate_callgraph", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Delegate to `/cortex-core:research`:", "research"),
        ("1. Invoke `/ui-lint`", "ui-lint"),
        ("Invoke the `/cortex-core:commit` skill to commit all changes", "commit"),
        ("invoke the `critical-review` skill with the plan artifact", "critical-review"),
        ("dispatch the `/cortex-core:refine` skill now", "refine"),
        ("Delegate to `/cortex-overnight:overnight`:", "overnight"),
        ("Invoke the `/cortex-overnight:morning-review` skill", "morning-review"),
        ("see the `research.md` file", None),
        ("the `/cortex-core:research` output was useful", None),
    ],
)
def test_invocation_regex(module, line, expected):
    match = module.INVOCATION_RE.search(line)
    if expected is None:
        assert match is None, f"unexpected match on {line!r}: {match.group(0)}"
    else:
        assert match is not None, f"expected match on {line!r}"
        assert match.group(1) == expected


def test_real_tree_clean(tmp_path):
    """The live skills/ and .claude/skills/ trees must have no violations."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "skills", ".claude/skills"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"call-graph check failed:\n{result.stdout}\n{result.stderr}"
    )


def test_detects_disabled_callee(tmp_path):
    """A synthetic skill tree with a known violation must fail the check."""
    caller = tmp_path / "caller"
    callee = tmp_path / "callee"
    caller.mkdir()
    callee.mkdir()
    (caller / "SKILL.md").write_text(
        "---\nname: caller\ndescription: x\n---\n\nInvoke `/callee` to do the thing.\n"
    )
    (callee / "SKILL.md").write_text(
        "---\nname: callee\ndescription: x\ndisable-model-invocation: true\n---\n\nbody\n"
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "/caller invokes /callee" in result.stdout
    assert "disable-model-invocation: true" in result.stdout


def test_ignores_suppression_comment(tmp_path):
    """A line annotated with the suppression marker must not trigger the check."""
    caller = tmp_path / "caller"
    callee = tmp_path / "callee"
    caller.mkdir()
    callee.mkdir()
    (caller / "SKILL.md").write_text(
        "---\nname: caller\ndescription: x\n---\n\n"
        "Invoke `/callee` to do the thing. <!-- callgraph: ignore -->\n"
    )
    (callee / "SKILL.md").write_text(
        "---\nname: callee\ndescription: x\ndisable-model-invocation: true\n---\n\nbody\n"
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{result.stdout}"
