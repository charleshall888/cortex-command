"""Enforces that feature_executor.py does not import from batch_runner or
orchestrator — prevents circular imports."""

import ast
import unittest
from pathlib import Path

_FEATURE_EXECUTOR_PATH = Path(__file__).resolve().parents[1] / "feature_executor.py"
_FORBIDDEN_PREFIXES = ("claude.overnight.batch_runner", "claude.overnight.orchestrator")


def _type_checking_guarded_linenos(tree: ast.Module) -> set[int]:
    """Return line numbers of import nodes inside `if TYPE_CHECKING:` guards.

    These are not runtime imports and do not create circular dependencies,
    so the boundary test excludes them.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    guarded.add(child.lineno)
    return guarded


class TestFeatureExecutorImportBoundary(unittest.TestCase):
    def test_no_forbidden_imports(self) -> None:
        source = _FEATURE_EXECUTOR_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        guarded = _type_checking_guarded_linenos(tree)
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.lineno in guarded:
                    continue
                module = node.module or ""
                for prefix in _FORBIDDEN_PREFIXES:
                    if module == prefix or module.startswith(prefix + "."):
                        violations.append(f"line {node.lineno}: from {module} import ...")
            elif isinstance(node, ast.Import):
                if node.lineno in guarded:
                    continue
                for alias in node.names:
                    for prefix in _FORBIDDEN_PREFIXES:
                        if alias.name == prefix or alias.name.startswith(prefix + "."):
                            violations.append(f"line {node.lineno}: import {alias.name}")
        if violations:
            self.fail(
                "feature_executor.py contains forbidden runtime imports:\n"
                + "\n".join(violations)
            )


if __name__ == "__main__":
    unittest.main()
