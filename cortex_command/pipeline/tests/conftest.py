"""Conftest: install the claude_agent_sdk stub before any test in this package.

This must run exactly once before dispatch is imported. Placing the stub
installation here (rather than in the test module) prevents the double-import
issue that arises when pytest's rootdir heuristic imports the test file under
two different fully-qualified names.
"""

from cortex_command.tests._stubs import _install_sdk_stub  # noqa: F401 — re-exported for test imports

_install_sdk_stub()
