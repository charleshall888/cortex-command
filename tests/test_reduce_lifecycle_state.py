"""Unit tests for ``cortex_command.common.reduce_lifecycle_state``.

The shared tolerant reducer is the single source of truth that
``state_cli``, ``read_tier``/``read_criticality``, and
``refine._reduce_current_state`` all delegate to. These tests pin the R1
acceptance cases: tolerant decoding, per-value vocabulary rejection, and
the ``skipped_lines`` signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.common import (
    LifecycleStateReduction,
    lifecycle_state_corrupted,
    read_criticality,
    read_tier,
    reduce_lifecycle_events,
    reduce_lifecycle_state,
)
from cortex_command.lifecycle import state_cli


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


def test_read_tier_non_utf8_does_not_raise(tmp_path):
    """read_tier/read_criticality flow through the tolerant reducer: a
    non-UTF-8 events.log returns a string rather than raising
    UnicodeDecodeError (spec R5)."""
    feature_dir = tmp_path / "feat-non-utf8"
    feature_dir.mkdir()
    (feature_dir / "events.log").write_bytes(
        b'{"event":"lifecycle_start","tier":"complex","criticality":"high"}\n'
        b"\xff\xfe torn \xfa\n"
    )
    tier = read_tier("feat-non-utf8", lifecycle_base=tmp_path)
    crit = read_criticality("feat-non-utf8", lifecycle_base=tmp_path)
    assert isinstance(tier, str) and tier == "complex"
    assert isinstance(crit, str) and crit == "high"


# ---------------------------------------------------------------------------
# Corruption signal (Task 5)
# ---------------------------------------------------------------------------


def _stage_log(root: Path, feature: str, *byte_lines: bytes) -> Path:
    """Write events.log bytes under root/cortex/lifecycle/<feature>/."""
    fdir = root / "cortex" / "lifecycle" / feature
    fdir.mkdir(parents=True, exist_ok=True)
    path = fdir / "events.log"
    path.write_bytes(b"".join(byte_lines))
    return path


def test_corrupt_torn_start_only_predicate_and_cli(tmp_path, monkeypatch, capsys):
    """Torn lifecycle_start-only: both axes unknowable. The predicate is true,
    and the corruption signal rides through BOTH the unfiltered and the
    --field tier CLI paths (the filtered path is what the gates read)."""
    _stage_log(tmp_path, "feat", b'{"event":"lifecycle_start","tier":"comp\n')
    base = tmp_path / "cortex" / "lifecycle"
    assert lifecycle_state_corrupted("feat", lifecycle_base=base) is True

    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        state_cli.main(["--feature", "feat"])
    assert exc.value.code == 0
    assert '"corrupted":true' in capsys.readouterr().out

    with pytest.raises(SystemExit):
        state_cli.main(["--feature", "feat", "--field", "tier"])
    assert capsys.readouterr().out.strip() == '{"corrupted":true}'


def test_corrupt_symmetric_criticality_axis_predicate_true(tmp_path):
    """Valid tier + mojibake criticality → criticality axis unknowable → corrupted
    (the symmetric R7 amendment: tier intact does not exempt the gate)."""
    base = tmp_path / "cortex" / "lifecycle"
    _stage_log(
        tmp_path,
        "feat-sym",
        '{"event":"lifecycle_start","tier":"complex","criticality":"�"}\n'.encode(
            "utf-8"
        ),
    )
    assert lifecycle_state_corrupted("feat-sym", lifecycle_base=base) is True


def test_corrupt_clean_no_state_predicate_false_no_cli_key(tmp_path, monkeypatch, capsys):
    """A clean log with no state events → not corrupted, no CLI key (additive)."""
    base = tmp_path / "cortex" / "lifecycle"
    _stage_log(
        tmp_path,
        "feat-clean",
        b'{"event":"phase_transition","from":"research","to":"specify"}\n',
    )
    assert lifecycle_state_corrupted("feat-clean", lifecycle_base=base) is False

    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        state_cli.main(["--feature", "feat-clean"])
    assert "corrupted" not in capsys.readouterr().out


def test_corrupt_torn_mid_file_recovered_predicate_false(tmp_path):
    """A torn line after a valid lifecycle_start → state recovered → not corrupted."""
    base = tmp_path / "cortex" / "lifecycle"
    _stage_log(
        tmp_path,
        "feat-mid",
        b'{"event":"lifecycle_start","tier":"complex","criticality":"high"}\n',
        b'{"event":"phase_transition","from":"resea\n',
    )
    assert lifecycle_state_corrupted("feat-mid", lifecycle_base=base) is False


def test_corrupt_missing_events_log_predicate_false(tmp_path):
    """Missing events.log → not corrupted (routine for stateless features at the
    overnight gate sites; a regression here would route every stateless feature
    to review)."""
    base = tmp_path / "cortex" / "lifecycle"
    assert lifecycle_state_corrupted("feat-missing", lifecycle_base=base) is False


def test_reduce_lifecycle_state_library_readers_silent_on_stderr(tmp_path, capsys):
    """CLI-only boundary (spec R9): read_tier on a torn file writes nothing to
    stderr — only state_cli surfaces skipped lines as warnings."""
    feature_dir = tmp_path / "feat-silent"
    feature_dir.mkdir()
    (feature_dir / "events.log").write_bytes(
        b'{"event":"lifecycle_start","tier":"complex","criticality":"high"}\n'
        b'{"event":"phase_transition","from":"resea\n'
    )
    read_tier("feat-silent", lifecycle_base=tmp_path)
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Pure-core entry point: reduce_lifecycle_events (feature 301)
# ---------------------------------------------------------------------------


def test_reduce_lifecycle_events_empty_input():
    """Empty input → empty state, no rejected positions."""
    state, rejected = reduce_lifecycle_events([])
    assert state == {}
    assert rejected == []


def test_reduce_lifecycle_events_seed_and_overrides_insertion_order():
    """Seed + complexity_override + criticality_override → both axes present in
    criticality-then-tier insertion order, no rejections."""
    state, rejected = reduce_lifecycle_events(
        [
            {"event": "lifecycle_start", "tier": "simple", "criticality": "medium"},
            {"event": "complexity_override", "to": "complex"},
            {"event": "criticality_override", "to": "high"},
        ]
    )
    assert state == {"criticality": "high", "tier": "complex"}
    assert list(state.keys()) == ["criticality", "tier"]
    assert rejected == []


def test_reduce_lifecycle_events_out_of_vocab_value_dropped_and_reported():
    """An out-of-vocab override value is dropped from state and its 0-based
    position is reported."""
    state, rejected = reduce_lifecycle_events(
        [
            {"event": "lifecycle_start", "tier": "simple"},
            {"event": "complexity_override", "to": "trivial"},
        ]
    )
    assert state == {"tier": "simple"}
    assert rejected == [1]


def test_reduce_lifecycle_events_non_dict_record_is_silent_noop():
    """A non-dict record is a silent no-op — no state change, NOT reported."""
    state, rejected = reduce_lifecycle_events(
        [42, {"event": "lifecycle_start", "tier": "complex"}]
    )
    assert state == {"tier": "complex"}
    assert rejected == []


def test_reduce_lifecycle_events_second_lifecycle_start_reseeds_tier():
    """A second lifecycle_start re-seeds state['tier'] (last writer wins)."""
    state, rejected = reduce_lifecycle_events(
        [
            {"event": "lifecycle_start", "tier": "simple"},
            {"event": "lifecycle_start", "tier": "complex"},
        ]
    )
    assert state["tier"] == "complex"
    assert rejected == []


def test_reduce_lifecycle_events_double_axis_rejection_reports_position_once():
    """A single lifecycle_start carrying BOTH an out-of-vocab tier AND an
    out-of-vocab criticality reports its position exactly once (not twice) —
    the per-record-once contract distinguishing per-record from per-value
    emission. The only input that catches a per-value double-append."""
    state, rejected = reduce_lifecycle_events(
        [{"event": "lifecycle_start", "tier": "trivial", "criticality": "bogus"}]
    )
    assert state == {}
    assert rejected == [0]


def test_reduce_lifecycle_state_double_axis_rejection_flags_line_once(tmp_path):
    """Through the Path reader, the double-out-of-vocab lifecycle_start's line
    appears once in skipped_lines."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"trivial","criticality":"bogus"}',
    )
    result = reduce_lifecycle_state(log)
    assert result.state == {}
    assert result.skipped_lines == (1,)


def test_reduce_lifecycle_state_interleaved_vocab_and_torn_ascending(tmp_path):
    """A vocab-rejected value on line 1 and a torn-JSON line 2 → skipped_lines
    is ascending (1, 2), not category-grouped."""
    log = tmp_path / "events.log"
    _write(
        log,
        '{"event":"lifecycle_start","tier":"trivial","criticality":"high"}',
        '{"event":"complexity_override","to":"comp',
    )
    result = reduce_lifecycle_state(log)
    assert result.skipped_lines == (1, 2)
    assert result.state == {"criticality": "high"}


def test_lifecycle_state_reduction_not_grown():
    """R3 growth guard: the NamedTuple keeps exactly its two declared fields.
    The missing-file equality assertion does NOT catch a defaulted added
    field, so this field-set assertion is the actual growth guard."""
    assert LifecycleStateReduction._fields == ("state", "skipped_lines")
