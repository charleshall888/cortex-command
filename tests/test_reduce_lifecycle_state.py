"""Unit tests for ``cortex_command.common.reduce_lifecycle_state``.

The shared tolerant reducer is the single source of truth that
``state_cli``, ``read_tier``/``read_criticality``, and
``refine._reduce_current_state`` all delegate to. These tests pin the R1
acceptance cases: tolerant decoding, per-value vocabulary rejection, and
the ``skipped_lines`` signal.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.common import (
    LifecycleStateReduction,
    reduce_lifecycle_state,
)


def _write(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_reduce_lifecycle_state_non_utf8_no_raise(tmp_path):
    """A non-UTF-8 byte sequence is decoded-and-skipped, never raised."""
    log = tmp_path / "events.log"
    log.write_bytes(
        b'{"event":"lifecycle_start","tier":"complex","criticality":"high"}\n'
        b"\xff\xfe not utf-8 \xfa\n"
    )
    result = reduce_lifecycle_state(log)
    assert isinstance(result, LifecycleStateReduction)
    assert result.state == {"criticality": "high", "tier": "complex"}
    assert 2 in result.skipped_lines


def test_reduce_lifecycle_state_out_of_vocab_override_ignored(tmp_path):
    """A mojibake override value must not overwrite a prior valid tier."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"complex","criticality":"high"}',
        '{"event":"complexity_override","to":"��"}',
    )
    result = reduce_lifecycle_state(log)
    assert result.state["tier"] == "complex"
    assert 2 in result.skipped_lines


def test_reduce_lifecycle_state_torn_line_skipped(tmp_path):
    """A torn (un-parseable) line is recorded by 1-based line number."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"simple","criticality":"medium"}',
        '{"event":"complexity_override","to":"comp',
    )
    result = reduce_lifecycle_state(log)
    assert result.skipped_lines == (2,)
    assert result.state == {"criticality": "medium", "tier": "simple"}


def test_reduce_lifecycle_state_clean_log_no_skips(tmp_path):
    """A fully valid log yields an empty ``skipped_lines`` tuple."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"simple","criticality":"medium"}',
        '{"event":"complexity_override","to":"complex"}',
        '{"event":"criticality_override","to":"high"}',
    )
    result = reduce_lifecycle_state(log)
    assert result.skipped_lines == ()
    assert result.state == {"criticality": "high", "tier": "complex"}


def test_reduce_lifecycle_state_mixed_line_per_value(tmp_path):
    """Per-value rejection: a valid tier accumulates even when the same line
    carries a mojibake criticality, and the line is still flagged."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"complex","criticality":"�"}',
    )
    result = reduce_lifecycle_state(log)
    assert result.state == {"tier": "complex"}
    assert result.skipped_lines == (1,)


def test_reduce_lifecycle_state_missing_file_is_empty(tmp_path):
    """A missing file reduces to an empty result and never raises."""
    result = reduce_lifecycle_state(tmp_path / "nope.log")
    assert result == LifecycleStateReduction(state={}, skipped_lines=())
