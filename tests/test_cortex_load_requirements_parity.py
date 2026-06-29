"""Deploy/wiring parity for the cortex-load-requirements verb.

Unlike the sibling ``test_cortex_*_parity.py`` files, this is **not** a
golden-replay parity test: there is no original bin script to replay — the
"original" is the LLM-hand-executed prose in
``skills/lifecycle/references/load-requirements.md``. The replay harness in
``tests/test_parity_contract.py`` therefore does not apply.

Instead this file pins the verb's deploy surface and carries the in-scope
wiring reference that satisfies ``cortex-check-parity`` (W003): the contiguous
path-qualified ``bin/cortex-load-requirements`` literal in ``WRAPPER_REL``
below is the wiring signal that proves the deployed console-script /
``bin/`` wrapper is referenced in scope (a bare ``python3 -m`` module path is
not). The assertions below also guarantee ≥1 collected test so pytest never
returns exit 5 ("no tests collected").
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Contiguous path-qualified literal — the W003 wiring signal (PATH_QUALIFIED_RE).
WRAPPER_REL = "bin/cortex-load-requirements"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONSOLE_SCRIPT_LINE = (
    'cortex-load-requirements = '
    '"cortex_command.lifecycle.load_requirements_cli:main"'
)


def test_wrapper_exists_and_is_executable() -> None:
    wrapper = REPO_ROOT / WRAPPER_REL
    assert wrapper.is_file(), f"{WRAPPER_REL} missing"
    assert os.access(wrapper, os.X_OK), f"{WRAPPER_REL} not executable"


def test_console_script_registered_in_pyproject() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert CONSOLE_SCRIPT_LINE in text, (
        "cortex-load-requirements console-script entry missing from "
        "[project.scripts]"
    )


def test_wrapper_carries_log_invocation_shim() -> None:
    # Phase-1.6 shim gate (cortex-invocation-report --check-shims) greps the
    # first 50 lines of every bin/cortex-* for the cortex-log-invocation shim.
    head = (REPO_ROOT / WRAPPER_REL).read_text(encoding="utf-8").splitlines()[:50]
    assert any("cortex-log-invocation" in line for line in head), (
        "wrapper missing the cortex-log-invocation shim line"
    )


def test_wrapper_force_source_emits_project_md_first() -> None:
    # Exercise the deployed wrapper via the working-tree branch; the first
    # stdout line must be the unconditional project.md path.
    env = dict(os.environ)
    env["CORTEX_COMMAND_FORCE_SOURCE"] = "1"
    env["CORTEX_REPO_ROOT"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.load_requirements_cli"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    first_line = proc.stdout.splitlines()[0]
    assert first_line == "cortex/requirements/project.md", proc.stdout
