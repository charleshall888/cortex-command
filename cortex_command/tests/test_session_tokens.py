"""Tests for cortex-session-tokens (#392) — read usage, classify nothing.

Pins the four non-negotiable contract rules with hand-computed arithmetic:
dedup by billed ``message.id`` before any sum, the per-TTL price table (with
the breakdown-absent → 1h-rate fallback), the file-path orchestrator/subagent
split, and the loud ``unpriced_requests`` handling for a model outside the
table (counted, never silently priced). Plus the two durable aggregates (the
log-log fit and the subagent tail) and the CLI envelope.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from cortex_command import session_tokens as st


def _record(
    mid: str,
    *,
    model: str = "claude-opus-4-8",
    inp: int = 0,
    out: int = 0,
    read: int = 0,
    w5: int = 0,
    w1h: int = 0,
    bare_write: int = 0,
) -> dict:
    usage: dict = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
    }
    if w5 or w1h:
        usage["cache_creation"] = {
            "ephemeral_5m_input_tokens": w5,
            "ephemeral_1h_input_tokens": w1h,
        }
    if bare_write:
        usage["cache_creation_input_tokens"] = bare_write
    return {"type": "assistant", "message": {"id": mid, "model": model, "usage": usage}}


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# ---------------------------------------------------------------------------
# Dedup — the single most consequential rule
# ---------------------------------------------------------------------------


def test_dedup_by_message_id(tmp_path: Path) -> None:
    """Three JSONL records sharing one message.id (one per content block, same
    cumulative usage) count as ONE billed request — never summed thrice."""
    rec = _record("msg_a", inp=100, out=50)
    _write_jsonl(tmp_path / "s.jsonl", [rec, rec, rec, _record("msg_b", inp=10)])
    rows = st.scan_file(tmp_path / "s.jsonl")
    assert len(rows) == 2
    agg = st._aggregate(rows)
    assert agg["requests"] == 2
    assert agg["input_tokens"] == 110


def test_dedup_falls_back_to_request_id_then_uuid(tmp_path: Path) -> None:
    a = {"type": "assistant", "requestId": "req_1",
         "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 1}}}
    b = {"type": "assistant", "uuid": "u1",
         "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 2}}}
    _write_jsonl(tmp_path / "s.jsonl", [a, a, b])
    assert len(st.scan_file(tmp_path / "s.jsonl")) == 2


def test_scan_tolerates_torn_lines_and_non_assistant(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    p.write_text(
        "{torn\n"
        + json.dumps({"type": "user", "message": {"usage": {"input_tokens": 9}}}) + "\n"
        + json.dumps(_record("msg_a", inp=5)) + "\n",
        encoding="utf-8",
    )
    rows = st.scan_file(p)
    assert len(rows) == 1 and rows[0]["usage"]["input_tokens"] == 5


# ---------------------------------------------------------------------------
# Pricing — table + per-TTL split + fallback + unpriced loudness
# ---------------------------------------------------------------------------


def test_cost_arithmetic_per_ttl_split() -> None:
    """Hand-computed: opus 1M of everything → inp 5 + out 25 + w5 6.25 +
    w1h 10 + read 0.5 dollars."""
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 1_000_000,
            "ephemeral_1h_input_tokens": 1_000_000,
        },
    }
    assert st._cost(usage, "claude-opus-4-8") == pytest.approx(46.75)


def test_cost_fallback_charges_bare_total_at_1h_rate() -> None:
    """No cache_creation breakdown: the bare total bills at the 1h (2x) rate —
    the conservative bound the verified prototype used."""
    usage = {"cache_creation_input_tokens": 1_000_000}
    assert st._cost(usage, "claude-sonnet-5") == pytest.approx(6.0)


def test_unknown_model_is_counted_but_never_priced(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "s.jsonl", [
        _record("msg_a", model="future-model-9", inp=1_000_000),
        _record("msg_b", model="claude-haiku-4-5", inp=1_000_000),
    ])
    agg = st._aggregate(st.scan_file(tmp_path / "s.jsonl"))
    assert agg["requests"] == 2
    assert agg["unpriced_requests"] == 1
    assert agg["input_tokens"] == 2_000_000  # tokens still counted
    assert agg["cost_usd"] == pytest.approx(1.0)  # only the haiku request billed


def test_peak_context_is_max_request_context(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "s.jsonl", [
        _record("msg_a", inp=1_000, read=200_000, w1h=5_000),
        _record("msg_b", inp=2_000, read=50_000),
    ])
    agg = st._aggregate(st.scan_file(tmp_path / "s.jsonl"))
    assert agg["peak_context_tokens"] == 206_000


# ---------------------------------------------------------------------------
# Orchestrator/subagent split by file path + report assembly
# ---------------------------------------------------------------------------


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    _write_jsonl(proj / "sess1.jsonl", [_record("m1", inp=100, out=10, read=1000)])
    _write_jsonl(proj / "sess1" / "subagents" / "a.jsonl",
                 [_record(f"a{i}", out=5, read=100 * (i + 1)) for i in range(4)])
    _write_jsonl(proj / "sess1" / "subagents" / "b.jsonl", [_record("b0", out=1)])
    return proj


def test_report_splits_main_and_subagents_by_path(tmp_path: Path) -> None:
    report = st.build_report(_project(tmp_path))
    assert report["totals"]["sessions"] == 1
    s = report["sessions"][0]
    assert s["session"] == "sess1"
    assert s["main"]["requests"] == 1
    assert s["subagents"]["agents"] == 2
    assert s["subagents"]["requests"] == 5
    assert s["total_cost_usd"] == pytest.approx(
        s["main"]["cost_usd"] + s["subagents"]["cost_usd"]
    )
    tail = report["subagent_tail"]
    assert tail["agents"] == 2
    assert tail["turns"]["p50"] == 1 and tail["turns"]["p99"] == 4


def test_session_filter_limits_to_one_transcript(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    _write_jsonl(proj / "sess2.jsonl", [_record("m2", inp=1)])
    full = st.build_report(proj)
    one = st.build_report(proj, session_id="sess2")
    assert full["totals"]["sessions"] == 2
    assert [s["session"] for s in one["sessions"]] == ["sess2"]


# ---------------------------------------------------------------------------
# The log-log fit
# ---------------------------------------------------------------------------


def test_loglog_fit_recovers_known_exponent() -> None:
    xs = [1.0, 2.0, 4.0, 8.0, 16.0]
    ys = [x ** 1.68 for x in xs]
    fit = st.loglog_fit(xs, ys)
    assert fit is not None
    assert fit["k"] == pytest.approx(1.68, abs=0.001)
    assert fit["r"] == pytest.approx(1.0, abs=0.001)
    assert fit["n"] == 5


def test_loglog_fit_refuses_degenerate_input() -> None:
    assert st.loglog_fit([1.0, 2.0], [1.0, 2.0]) is None  # n < 3
    assert st.loglog_fit([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # constant axis
    assert st.loglog_fit([0.0, 1.0, 2.0], [1.0, 2.0], ) is None  # zipped short/zeros


# ---------------------------------------------------------------------------
# CLI envelope
# ---------------------------------------------------------------------------


def test_cli_json_and_human_outputs(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)
    assert st.main(["--project-dir", str(proj), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["totals"]["sessions"] == 1

    assert st.main(["--project-dir", str(proj)]) == 0
    human = capsys.readouterr().out
    assert "sess1" in human and "total: 1 sessions" in human


def test_cli_warns_loudly_on_unpriced_models(tmp_path: Path, capsys) -> None:
    proj = tmp_path / "proj"
    _write_jsonl(proj / "s.jsonl", [_record("m", model="mystery", inp=10)])
    assert st.main(["--project-dir", str(proj)]) == 0
    assert "understate" in capsys.readouterr().out


def test_cli_exits_1_on_missing_project_dir(tmp_path: Path, capsys) -> None:
    assert st.main(["--project-dir", str(tmp_path / "nope")]) == 1
    assert "no project dir" in capsys.readouterr().err
