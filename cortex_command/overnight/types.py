"""Shared data types for the overnight runner.

This module imports only from stdlib and third-party packages.
No cortex_command.overnight.* imports are allowed here.

FeatureResult status-to-field mapping:
  merged           — no optional fields set
  repair_completed — repair_branch, trivial_resolved, resolved_files, repair_agent_used
  paused           — error required; parse_error may be True
  deferred         — deferred_question_count set
  failed           — error required
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeatureResult:
    """Result of executing a single feature."""

    name: str
    status: str  # merged, paused, deferred, failed, repair_completed
    error: Optional[str] = None
    deferred_question_count: int = 0
    files_changed: list[str] = field(default_factory=list)
    repair_branch: Optional[str] = None
    trivial_resolved: bool = False
    repair_agent_used: bool = False
    parse_error: bool = False
    resolved_files: list[str] = field(default_factory=list)


@dataclass
class CircuitBreakerState:
    """Tracks circuit breaker state across feature executions."""

    consecutive_pauses: int = 0
