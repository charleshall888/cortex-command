"""Structural test: verifies that in bin/cortex-log-invocation the working-tree
pyproject grep predicate (branch b) appears before the wheel-import probe (branch c).

This is a file-content assertion with no runtime cost — it locks the branch ordering
established in the perf optimisation that avoids a double Python boot on dev checkouts.
"""

from pathlib import Path


def test_bash_branch_order():
    lines = Path("bin/cortex-log-invocation").read_text().splitlines()

    pyproject_anchor = '^name = "cortex-command"'
    wheel_anchor = 'import cortex_command.log_invocation"'

    pyproject_idx = next(
        (i for i, line in enumerate(lines) if pyproject_anchor in line), None
    )
    wheel_idx = next(
        (i for i, line in enumerate(lines) if wheel_anchor in line), None
    )

    assert pyproject_idx is not None, (
        f"Working-tree pyproject anchor {pyproject_anchor!r} not found in "
        "bin/cortex-log-invocation"
    )
    assert wheel_idx is not None, (
        f"Wheel-import probe anchor {wheel_anchor!r} not found in "
        "bin/cortex-log-invocation"
    )
    assert pyproject_idx < wheel_idx, (
        f"Expected working-tree pyproject check (line {pyproject_idx + 1}) to appear "
        f"before wheel-import probe (line {wheel_idx + 1}) in bin/cortex-log-invocation"
    )
