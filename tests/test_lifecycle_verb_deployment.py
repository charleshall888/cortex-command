"""Deployment/wiring test for the lifecycle wrapper verbs (corpus-trim wave 2).

One row per deployed verb: asserts its ``[project.scripts]`` console entry and
its executable ``bin/`` wrapper. Living under the top-level ``tests/`` tree puts
each ``bin/cortex-...`` reference in the parity linter's scan surface
(SCAN_GLOBS: ``tests/**/*.py``), which is the honest in-scope wiring signal for
the deployed scripts — the same pattern by which
``tests/test_cortex_lifecycle_counters_parity.py`` wires
``bin/cortex-lifecycle-counters``.

Extending (Tasks 2/3): when the enter and finalize verbs are deployed, append
their ``(console_script, entry_point, bin_rel)`` tuples to ``VERBS``. Do NOT add
a row before its pyproject row and ``bin/`` wrapper both exist — the parity
linter would otherwise flag E002 (referenced-but-not-deployed), and the literal
verb name must not appear anywhere in this file until then.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (console_script, entry_point, bin_rel). ``bin_rel`` is a contiguous
# "bin/cortex-..." literal so the parity linter's PATH_QUALIFIED_RE registers
# the wiring signal for each deployed script from this in-scope file.
VERBS: list[tuple[str, str, str]] = [
    (
        "cortex-lifecycle-register-artifact",
        "cortex_command.lifecycle.register_artifact:main",
        "bin/cortex-lifecycle-register-artifact",
    ),
    (
        "cortex-lifecycle-enter",
        "cortex_command.lifecycle.enter:main",
        "bin/cortex-lifecycle-enter",
    ),
]


def _console_scripts() -> dict[str, str]:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["scripts"]


@pytest.mark.parametrize("console_script, entry_point, bin_rel", VERBS)
def test_console_script_row_exists(console_script: str, entry_point: str, bin_rel: str) -> None:
    """The [project.scripts] row points at the verb's module main()."""
    assert _console_scripts().get(console_script) == entry_point


@pytest.mark.parametrize("console_script, entry_point, bin_rel", VERBS)
def test_bin_wrapper_present_and_executable(console_script: str, entry_point: str, bin_rel: str) -> None:
    """The dual-channel bin wrapper ships and is executable."""
    wrapper = REPO_ROOT / bin_rel
    assert wrapper.is_file()
    assert os.access(wrapper, os.X_OK)


@pytest.mark.parametrize("console_script, entry_point, bin_rel", VERBS)
def test_bin_wrapper_execs_module(console_script: str, entry_point: str, bin_rel: str) -> None:
    """The wrapper dispatches to the verb's module (not a stale name)."""
    module = entry_point.split(":", 1)[0]
    assert module in (REPO_ROOT / bin_rel).read_text(encoding="utf-8")
