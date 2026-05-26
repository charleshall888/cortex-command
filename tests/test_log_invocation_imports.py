"""Import-discipline and session-id-first ordering tests for log_invocation.

Two structural invariants introduced by the Task 4 refactor:

1. ``test_log_invocation_no_top_level_heavy_imports`` — the module must NOT
   import ``subprocess``, ``datetime``, ``json``, or ``pathlib`` at the
   top level (module import time). Uses subprocess isolation so that modules
   already loaded in the parent pytest process cannot produce a false pass.

2. ``test_log_invocation_main_session_id_check_first`` — the first executable
   statement inside ``main()`` (after an optional docstring) must be an
   assignment whose right-hand side calls ``os.environ.get`` with the literal
   argument ``"LIFECYCLE_SESSION_ID"``. Verified via ``ast.parse`` — no
   subprocess, no runtime cost.

Both tests are skipped pending the Task 4 module refactor. Task 4 removes
both ``@pytest.mark.skip`` decorators to activate the assertions.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "cortex_command" / "log_invocation.py"

_HEAVY_MODULES = ("subprocess", "datetime", "json", "pathlib")


@pytest.mark.skip(reason="awaiting refactor in task 4")
def test_log_invocation_no_top_level_heavy_imports() -> None:
    """Importing the module must not bring subprocess/datetime/json/pathlib into sys.modules.

    Uses a fresh subprocess so modules already loaded in the parent pytest
    process cannot mask a top-level import violation. The test enforces
    top-level discipline only — these modules may appear in sys.modules once
    ``main()`` has been called (lazy imports inside functions are fine).
    """
    probe = (
        "import sys; "
        "import cortex_command.log_invocation; "
        "heavy = [m for m in {modules!r} if m in sys.modules]; "
        "sys.exit(1 if heavy else 0)"
    ).format(modules=list(_HEAVY_MODULES))

    result = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Top-level heavy imports detected after importing "
        f"cortex_command.log_invocation.\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )


@pytest.mark.skip(reason="awaiting refactor in task 4")
def test_log_invocation_main_session_id_check_first() -> None:
    """The first executable statement in main() must assign os.environ.get("LIFECYCLE_SESSION_ID", ...).

    Parsed structurally via ``ast`` — no subprocess, no runtime cost. Accepts
    either an ``ast.Assign`` or a bare ``ast.Expr`` whose call's first
    argument is the string literal ``"LIFECYCLE_SESSION_ID"``.
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE_PATH))

    # Locate the FunctionDef named 'main'
    main_node: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_node = node
            break

    assert main_node is not None, "Could not find 'main' FunctionDef in log_invocation.py"

    body = list(main_node.body)

    # Skip a leading docstring (ast.Expr whose value is a string constant)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]

    assert body, "main() has no executable statements after optional docstring"

    first = body[0]

    # Extract the call node from either Assign or Expr
    call_node: ast.Call | None = None
    if isinstance(first, ast.Assign):
        if isinstance(first.value, ast.Call):
            call_node = first.value
    elif isinstance(first, ast.Expr):
        if isinstance(first.value, ast.Call):
            call_node = first.value

    assert call_node is not None, (
        f"First executable statement in main() is not an assignment or expression "
        f"containing a call; got {ast.dump(first)!r}"
    )

    # The call must be os.environ.get(...)
    func = call_node.func
    is_environ_get = (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )
    assert is_environ_get, (
        f"First executable call in main() is not os.environ.get(...); "
        f"got {ast.dump(func)!r}"
    )

    # The first positional argument must be the literal "LIFECYCLE_SESSION_ID"
    assert call_node.args, (
        "os.environ.get call in main() has no positional arguments"
    )
    first_arg = call_node.args[0]
    assert (
        isinstance(first_arg, ast.Constant)
        and first_arg.value == "LIFECYCLE_SESSION_ID"
    ), (
        f"First argument to os.environ.get is not 'LIFECYCLE_SESSION_ID'; "
        f"got {ast.dump(first_arg)!r}"
    )
