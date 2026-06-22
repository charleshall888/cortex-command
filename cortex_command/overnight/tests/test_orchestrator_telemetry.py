"""Tests for orchestrator stream-json NDJSON result selection (spec Req 13).

Phase 2 of ``overnight-watchdogthread-is-a-blind-30`` switches the
orchestrator to ``--output-format=stream-json --verbose
--include-partial-messages`` (Task 6). Its stdout is therefore an NDJSON
stream: ``system``/``assistant``/``user`` events, interleaved
``stream_event`` partial-message chunks, and a terminal ``type:"result"``
object that is shape-identical to today's ``--output-format=json``
envelope.

Task 5 (this module) lands the telemetry PARSER change FIRST so that when
Task 6 flips the flag the healthy-round telemetry still parses: the
selector ``_select_orchestrator_result_envelope`` picks the LAST line whose
top-level ``type == "result"``, skipping every non-result, blank, and
non-JSON line, and ``_emit_orchestrator_round_telemetry`` consumes that
selection. The legacy ``test_orchestrator_round_telemetry.py`` covers the
single-line ``--output-format=json`` envelope path; this module covers the
multi-line stream-json path and the selector's discrimination rules.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.overnight.runner import (
    _emit_orchestrator_round_telemetry,
    _select_orchestrator_result_envelope,
)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _result_envelope(
    *,
    cost_usd: float,
    is_error: bool = False,
    subtype: str = "success",
    output_tokens: int = 612,
) -> dict:
    """A terminal ``type:"result"`` object, shape-identical to the json envelope."""
    return {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "duration_ms": 18432,
        "num_turns": 4,
        "result": "Round complete.",
        "stop_reason": "end_turn",
        "total_cost_usd": cost_usd,
        "usage": {
            "input_tokens": 1842,
            "cache_creation_input_tokens": 5120,
            "cache_read_input_tokens": 23450,
            "output_tokens": output_tokens,
        },
        "model": "claude-opus-4-7",
    }


def _stream_json_fixture(terminal: dict) -> str:
    """Build a realistic stream-json NDJSON stream ending in ``terminal``.

    The stream interleaves the line shapes the runner must skip:
      - a ``system``/``init`` line,
      - an ``assistant`` message line,
      - ``stream_event`` partial-message chunk lines
        (from ``--include-partial-messages``),
      - a DECOY ``type:"result"``-SHAPED line whose top-level ``type`` is NOT
        ``"result"`` (it is ``"system"``) — must be skipped,
      - a DECOY EARLIER ``type:"result"`` object with DIFFERENT field values —
        proves "last result wins" rather than "first result",
      - a blank line and a non-JSON garbage line — must be tolerated,
      - the terminal ``type:"result"`` object.
    """
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "working"}]},
            }
        ),
        json.dumps(
            {"type": "stream_event", "event": {"type": "content_block_delta"}}
        ),
        json.dumps(
            {"type": "stream_event", "event": {"type": "content_block_delta"}}
        ),
        # Result-SHAPED but wrong top-level type: must be skipped.
        json.dumps(
            {
                "type": "system",
                "subtype": "result",
                "is_error": True,
                "total_cost_usd": 99.99,
                "usage": {"output_tokens": 1},
                "model": "decoy-shaped",
            }
        ),
        # Earlier genuine type:"result" with different values: must NOT win.
        json.dumps(
            _result_envelope(cost_usd=0.0001, output_tokens=1)
        ),
        json.dumps(
            {"type": "stream_event", "event": {"type": "content_block_delta"}}
        ),
        "",
        "this is not json {{{",
        json.dumps(terminal),
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Selector unit tests
# ---------------------------------------------------------------------------


def test_selector_picks_last_terminal_result() -> None:
    """The LAST type:"result" object is selected from a multi-line stream."""
    terminal = _result_envelope(cost_usd=0.0421, output_tokens=612)
    stream = _stream_json_fixture(terminal)

    selected = _select_orchestrator_result_envelope(stream)

    assert isinstance(selected, dict)
    assert selected.get("type") == "result"
    # The terminal result wins over the earlier genuine result (0.0001) and
    # the result-SHAPED system decoy (99.99).
    assert selected["total_cost_usd"] == 0.0421
    assert selected["usage"]["output_tokens"] == 612
    assert selected["model"] == "claude-opus-4-7"


def test_selector_single_line_json_envelope_unchanged() -> None:
    """A single-line --output-format=json envelope (type:"result") is selected."""
    envelope = _result_envelope(cost_usd=0.5, output_tokens=300)
    selected = _select_orchestrator_result_envelope(json.dumps(envelope))

    assert isinstance(selected, dict)
    assert selected["total_cost_usd"] == 0.5
    assert selected["usage"]["output_tokens"] == 300


def test_selector_skips_decoy_shaped_non_result_line() -> None:
    """A result-shaped line whose top-level type != result is never selected."""
    decoy = json.dumps(
        {
            "type": "assistant",
            "subtype": "result",
            "total_cost_usd": 12.34,
            "usage": {"output_tokens": 7},
        }
    )
    terminal = _result_envelope(cost_usd=0.07)
    stream = decoy + "\n" + json.dumps(terminal) + "\n"

    selected = _select_orchestrator_result_envelope(stream)

    assert selected["total_cost_usd"] == 0.07


def test_selector_no_json_lines_raises() -> None:
    """An all-garbage stream raises so the caller maps it to parse_failure."""
    try:
        _select_orchestrator_result_envelope("garbage {{{\n\nnot json either")
    except ValueError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected ValueError for an all-garbage stream")


# ---------------------------------------------------------------------------
# End-to-end through _emit_orchestrator_round_telemetry
# ---------------------------------------------------------------------------


def test_multiline_stream_success_emits_dispatch_complete(
    tmp_path: Path,
) -> None:
    """A multi-line stream-json stream emits dispatch_complete from the terminal."""
    terminal = _result_envelope(cost_usd=0.0421, output_tokens=612)
    stream = _stream_json_fixture(terminal)
    log_path = tmp_path / "pipeline-events.log"

    _emit_orchestrator_round_telemetry(
        envelope_text=stream,
        exit_code=0,
        round_num=1,
        log_path=log_path,
    )

    records = _read_jsonl(log_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == "dispatch_complete"
    assert rec["feature"] == "<orchestrator-round-1>"
    # Fields come from the TERMINAL result, not the earlier decoy (0.0001).
    assert rec["cost_usd"] == 0.0421
    assert rec["output_tokens"] == 612
    assert rec["model"] == "claude-opus-4-7"


def test_multiline_stream_is_error_terminal_emits_dispatch_error(
    tmp_path: Path,
) -> None:
    """A terminal result with is_error=True classifies as dispatch_error."""
    terminal = _result_envelope(cost_usd=0.0, is_error=True, subtype="success")
    stream = _stream_json_fixture(terminal)
    log_path = tmp_path / "pipeline-events.log"

    _emit_orchestrator_round_telemetry(
        envelope_text=stream,
        exit_code=0,
        round_num=2,
        log_path=log_path,
    )

    records = _read_jsonl(log_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == "dispatch_error"
    assert rec["details"]["reason"] == "is_error"


def test_multiline_stream_error_subtype_terminal_emits_dispatch_error(
    tmp_path: Path,
) -> None:
    """A terminal result whose subtype starts with error_ classifies as error."""
    terminal = _result_envelope(
        cost_usd=0.0, is_error=False, subtype="error_during_execution"
    )
    stream = _stream_json_fixture(terminal)
    log_path = tmp_path / "pipeline-events.log"

    _emit_orchestrator_round_telemetry(
        envelope_text=stream,
        exit_code=0,
        round_num=3,
        log_path=log_path,
    )

    records = _read_jsonl(log_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == "dispatch_error"
    assert rec["details"]["reason"] == "is_error"
