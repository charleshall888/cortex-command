"""Pipeline orchestrator for async multi-feature development.

Coordinates parallel feature implementation across isolated git worktrees
using the Claude Agent SDK, with retry logic, sequential merge-to-main,
and integration testing.
"""

__version__ = "0.1.0"
