"""Overnight orchestration strategy schema and persistence.

Defines the OvernightStrategy dataclass for tracking cross-round integration
health, hot files, recovery notes, and round history. Persistence functions
(save_strategy / load_strategy) use atomic writes via tempfile + os.replace
to prevent corruption on crash.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class OvernightStrategy:
    """Cross-round strategy state for an overnight session.

    Fields:
        hot_files: Files touched by 2+ features this session.
        integration_health: Overall integration branch health;
            either "healthy" or "degraded".
        recovery_log_summary: Human-readable summary of recovery actions
            taken during the session.
        round_history_notes: One entry per completed round, capturing
            notable events or decisions.
    """

    hot_files: list[str] = field(default_factory=list)
    integration_health: str = "healthy"
    recovery_log_summary: str = ""
    round_history_notes: list[str] = field(default_factory=list)


def load_strategy(path: Path) -> OvernightStrategy:
    """Read overnight strategy from a JSON file.

    Returns a default OvernightStrategy on any read or parse failure,
    including missing file, invalid JSON, or unexpected data shape.

    Args:
        path: Path to the overnight-strategy.json file.

    Returns:
        Deserialized OvernightStrategy, or a fresh default instance on error.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return OvernightStrategy()
    except json.JSONDecodeError:
        return OvernightStrategy()

    try:
        return OvernightStrategy(
            hot_files=raw.get("hot_files", []),
            integration_health=raw.get("integration_health", "healthy"),
            recovery_log_summary=raw.get("recovery_log_summary", ""),
            round_history_notes=raw.get("round_history_notes", []),
        )
    except (KeyError, TypeError, ValueError):
        return OvernightStrategy()


def save_strategy(strategy: OvernightStrategy, path: Path) -> None:
    """Atomically write overnight strategy to a JSON file.

    Writes to a temporary file in the same directory, then renames via
    os.replace. This prevents readers from seeing a partially-written file.

    Args:
        strategy: The OvernightStrategy to persist.
        path: Destination path for the JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(strategy)
    payload = json.dumps(data, indent=2) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".overnight-strategy-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, path)
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
