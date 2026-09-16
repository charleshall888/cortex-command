"""Pipeline orchestrator for async multi-feature development.

Coordinates parallel feature implementation across isolated git worktrees
by spawning the operator's ``claude`` CLI directly, with retry logic,
sequential merge-to-main, and integration testing.
"""

__version__ = "0.1.0"
