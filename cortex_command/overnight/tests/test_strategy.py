"""Unit tests for load_strategy() and save_strategy() in claude.overnight.strategy.

Uses tmp_path fixture for isolated filesystem — no git operations, no SDK calls.
"""

import dataclasses
import json
from pathlib import Path

from claude.overnight.strategy import OvernightStrategy, load_strategy, save_strategy


# ---------------------------------------------------------------------------
# test_load_absent_returns_defaults
# ---------------------------------------------------------------------------

def test_load_absent_returns_defaults(tmp_path: Path) -> None:
    """load_strategy returns default OvernightStrategy when the file does not exist."""
    result = load_strategy(tmp_path / "strategy.json")
    assert result.hot_files == []
    assert result.integration_health == "healthy"
    assert result.recovery_log_summary == ""
    assert result.round_history_notes == []


# ---------------------------------------------------------------------------
# test_load_valid_file
# ---------------------------------------------------------------------------

def test_load_valid_file(tmp_path: Path) -> None:
    """load_strategy correctly deserializes a valid JSON strategy file."""
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(
        json.dumps({
            "hot_files": ["a.py", "b.py"],
            "integration_health": "degraded",
            "recovery_log_summary": "tried once",
            "round_history_notes": ["round 1: ok"],
        }),
        encoding="utf-8",
    )
    result = load_strategy(strategy_path)
    assert result.hot_files == ["a.py", "b.py"]
    assert result.integration_health == "degraded"
    assert result.recovery_log_summary == "tried once"
    assert result.round_history_notes == ["round 1: ok"]


# ---------------------------------------------------------------------------
# test_save_roundtrip
# ---------------------------------------------------------------------------

def test_save_roundtrip(tmp_path: Path) -> None:
    """save_strategy followed by load_strategy returns an equal OvernightStrategy."""
    strategy_path = tmp_path / "strategy.json"
    original = OvernightStrategy(
        hot_files=["x.py"],
        integration_health="degraded",
        recovery_log_summary="r",
        round_history_notes=["n1"],
    )
    save_strategy(original, strategy_path)
    loaded = load_strategy(strategy_path)
    assert dataclasses.asdict(loaded) == dataclasses.asdict(original)


# ---------------------------------------------------------------------------
# test_load_malformed_json_returns_defaults
# ---------------------------------------------------------------------------

def test_load_malformed_json_returns_defaults(tmp_path: Path) -> None:
    """load_strategy returns defaults without raising when JSON is malformed."""
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text("not-valid-json", encoding="utf-8")
    result = load_strategy(strategy_path)
    assert result.hot_files == []
    assert result.integration_health == "healthy"
    assert result.recovery_log_summary == ""
    assert result.round_history_notes == []
