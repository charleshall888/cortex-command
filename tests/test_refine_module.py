"""Unit tests for ``cortex_command.refine`` (spec R1, R2, R3, R5, R11).

Covers the ``emit-lifecycle-start`` subcommand:

  - R1: ``test_emit_lifecycle_start_writes_backlog_values`` — backlog
    ``criticality: high`` + ``complexity: complex`` → row matches.
  - R2: ``test_emit_lifecycle_start_defaults`` — parametrized over
    missing criticality, missing complexity, no backlog file.
  - R3: ``test_emit_lifecycle_start_idempotent`` — pre-seeded events.log
    with a ``lifecycle_start`` row → second invocation no-ops.
  - R5: ``test_emit_lifecycle_start_rejects_invalid_value`` —
    parametrized over ``criticality: extreme`` and ``complexity: enormous``
    (unknown value). Legacy vocabulary (``trivial``/``medium``/``moderate``)
    is coerced, not rejected — see
    ``test_emit_lifecycle_start_coerces_legacy_complexity`` (#369).
  - R11: ``test_emit_lifecycle_start_matches_227_repro_scenario`` —
    backlog with ``criticality: high`` + ``complexity: simple`` →
    ``read_criticality`` returns ``"high"`` and ``read_tier`` returns
    ``"simple"``.

Tests call ``main`` directly with ``monkeypatch.chdir(tmp_path)`` to
isolate the working directory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cortex_command.common import read_criticality, read_tier
from cortex_command.lifecycle.state_cli import _reduce_events
from cortex_command.refine import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_backlog(tmp_path: Path, slug: str, frontmatter_lines: list[str]) -> Path:
    """Write a ``cortex/backlog/{slug}.md`` file with the given YAML lines."""
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    backlog_path = backlog_dir / f"{slug}.md"
    fm_block = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n# Body\n"
    backlog_path.write_text(fm_block, encoding="utf-8")
    return backlog_path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _events_log_path(tmp_path: Path, lifecycle_slug: str) -> Path:
    return tmp_path / "cortex" / "lifecycle" / lifecycle_slug / "events.log"


def _lifecycle_start_line(tier: str = "simple", criticality: str = "medium") -> str:
    """Return a serialized ``lifecycle_start`` row (the canonical seed)."""
    return json.dumps(
        {
            "schema_version": 3,
            "ts": "2026-01-01T00:00:00Z",
            "event": "lifecycle_start",
            "feature": "feat",
            "tier": tier,
            "criticality": criticality,
            "entry_point": "refine",
        }
    )


def _seed_events(tmp_path: Path, lifecycle_slug: str, lines: list[str]) -> Path:
    """Write ``events.log`` from raw serialized lines (one per row)."""
    events_log = _events_log_path(tmp_path, lifecycle_slug)
    events_log.parent.mkdir(parents=True, exist_ok=True)
    events_log.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return events_log


def _count_event(path: Path, event: str) -> int:
    """Count rows with ``event``, tolerating malformed lines (for the R5 case)."""
    count = 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event") == event:
            count += 1
    return count


# ---------------------------------------------------------------------------
# R1: emit-lifecycle-start writes backlog values
# ---------------------------------------------------------------------------


def test_emit_lifecycle_start_writes_backlog_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1: backlog ``criticality: high`` + ``complexity: complex`` → row matches."""
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "234-foo",
        ["title: Foo", "criticality: high", "complexity: complex"],
    )

    rc = main(
        [
            "emit-lifecycle-start",
            "--backlog-slug",
            "234-foo",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    events_log = _events_log_path(tmp_path, "feat")
    rows = _read_jsonl(events_log)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "lifecycle_start"
    assert row["feature"] == "feat"
    assert row["tier"] == "complex"
    assert row["criticality"] == "high"
    assert row["entry_point"] == "refine"
    assert row["schema_version"] == 1
    assert "ts" in row


# ---------------------------------------------------------------------------
# R2: defaults applied when backlog frontmatter is absent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario,frontmatter_lines,backlog_slug,expected_tier,expected_criticality",
    [
        (
            "missing_criticality",
            ["title: Foo", "complexity: complex"],
            "234-foo",
            "complex",
            "medium",
        ),
        (
            "missing_complexity",
            ["title: Foo", "criticality: high"],
            "234-foo",
            "simple",
            "high",
        ),
        (
            "no_backlog_file",
            None,
            None,
            "simple",
            "medium",
        ),
    ],
)
def test_emit_lifecycle_start_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    frontmatter_lines: list[str] | None,
    backlog_slug: str | None,
    expected_tier: str,
    expected_criticality: str,
) -> None:
    """R2: defaults applied when criticality/complexity/file absent."""
    monkeypatch.chdir(tmp_path)
    if frontmatter_lines is not None and backlog_slug is not None:
        _write_backlog(tmp_path, backlog_slug, frontmatter_lines)

    argv = ["emit-lifecycle-start", "--lifecycle-slug", "feat"]
    if backlog_slug is not None:
        argv.extend(["--backlog-slug", backlog_slug])

    rc = main(argv)
    assert rc == 0, f"scenario={scenario}"

    rows = _read_jsonl(_events_log_path(tmp_path, "feat"))
    assert len(rows) == 1, f"scenario={scenario}"
    row = rows[0]
    assert row["tier"] == expected_tier, f"scenario={scenario}"
    assert row["criticality"] == expected_criticality, f"scenario={scenario}"


# ---------------------------------------------------------------------------
# R3: idempotent on existing lifecycle_start row
# ---------------------------------------------------------------------------


def test_emit_lifecycle_start_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3: pre-seeded events.log → second invocation no-ops.

    File size and row count are unchanged after the second invocation.
    """
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "234-foo",
        ["title: Foo", "criticality: high", "complexity: complex"],
    )

    events_log = _events_log_path(tmp_path, "feat")
    events_log.parent.mkdir(parents=True, exist_ok=True)
    seed_row = {
        "schema_version": 1,
        "ts": "2026-01-01T00:00:00Z",
        "event": "lifecycle_start",
        "feature": "feat",
        "tier": "simple",
        "criticality": "low",
        "entry_point": "lifecycle",
    }
    events_log.write_text(json.dumps(seed_row) + "\n", encoding="utf-8")

    size_before = events_log.stat().st_size
    rows_before = _read_jsonl(events_log)

    rc = main(
        [
            "emit-lifecycle-start",
            "--backlog-slug",
            "234-foo",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    size_after = events_log.stat().st_size
    rows_after = _read_jsonl(events_log)
    assert size_after == size_before
    assert rows_after == rows_before
    # The pre-existing row's tier/criticality is preserved untouched.
    assert rows_after[0]["tier"] == "simple"
    assert rows_after[0]["criticality"] == "low"


# ---------------------------------------------------------------------------
# R5: invalid frontmatter values rejected with diagnostic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario,frontmatter_lines,bad_value",
    [
        (
            "criticality_extreme",
            ["title: Foo", "criticality: extreme", "complexity: simple"],
            "extreme",
        ),
        (
            "complexity_unknown_value",
            ["title: Foo", "criticality: high", "complexity: enormous"],
            "enormous",
        ),
    ],
)
def test_emit_lifecycle_start_rejects_invalid_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scenario: str,
    frontmatter_lines: list[str],
    bad_value: str,
) -> None:
    """R5: invalid frontmatter values cause non-zero exit with diagnostic.

    The handler calls ``sys.exit(64)`` from ``_read_backlog_frontmatter``;
    we catch ``SystemExit`` here and assert the code is non-zero. The
    diagnostic on stderr names the invalid value.
    """
    monkeypatch.chdir(tmp_path)
    _write_backlog(tmp_path, "234-foo", frontmatter_lines)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "emit-lifecycle-start",
                "--backlog-slug",
                "234-foo",
                "--lifecycle-slug",
                "feat",
            ]
        )

    assert exc_info.value.code != 0, f"scenario={scenario}"
    captured = capsys.readouterr()
    assert bad_value in captured.err, f"scenario={scenario}: stderr={captured.err!r}"
    assert "cortex-update-item" in captured.err, (
        f"scenario={scenario}: diagnostic must name the remediation command; "
        f"stderr={captured.err!r}"
    )


# ---------------------------------------------------------------------------
# Legacy complexity vocabulary coerced instead of hard-failing (#369)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "legacy_value,expected_tier",
    [
        ("trivial", "simple"),
        ("medium", "complex"),
        ("moderate", "complex"),
    ],
)
def test_emit_lifecycle_start_coerces_legacy_complexity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    legacy_value: str,
    expected_tier: str,
) -> None:
    """Pre-two-tier complexity values coerce with a stderr warning (#369).

    ``moderate``/``medium`` map to ``complex`` (clarify.md §5: when in
    doubt, prefer complex); ``trivial`` maps to ``simple``. The seed row
    carries the coerced tier and the command exits 0.
    """
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "111-legacy",
        ["title: Foo", "criticality: high", f"complexity: {legacy_value}"],
    )

    rc = main(
        [
            "emit-lifecycle-start",
            "--backlog-slug",
            "111-legacy",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    captured = capsys.readouterr()
    assert legacy_value in captured.err
    assert expected_tier in captured.err

    rows = _read_jsonl(_events_log_path(tmp_path, "feat"))
    assert rows[0]["tier"] == expected_tier
    assert rows[0]["criticality"] == "high"


def test_emit_lifecycle_start_treats_yaml_null_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``complexity: null`` / ``criticality: null`` fall back to defaults."""
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "112-null",
        ["title: Foo", "criticality: null", "complexity: null"],
    )

    rc = main(
        [
            "emit-lifecycle-start",
            "--backlog-slug",
            "112-null",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    rows = _read_jsonl(_events_log_path(tmp_path, "feat"))
    assert rows[0]["tier"] == "simple"
    assert rows[0]["criticality"] == "medium"


# ---------------------------------------------------------------------------
# R2 (#374): read-after-write verify matches anywhere, not by file tail
# ---------------------------------------------------------------------------


def test_emit_lifecycle_start_verify_tolerates_concurrent_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: a concurrent row landing between the seed write and the verify read
    does not cause a false ``read_after_write_mismatch``.

    The verify now matches the ``lifecycle_start`` row by ``event`` + ``feature``
    anywhere in the log rather than by file tail. We monkeypatch the module's
    ``log_event_at`` to append an unrelated concurrent row immediately after the
    genuine seed write, displacing the seed from the tail; the old tail-only
    assertion would have false-failed.
    """
    import cortex_command.refine as refine_module
    from cortex_command.lifecycle_event import log_event_at as real_log_event_at

    monkeypatch.chdir(tmp_path)

    def _wrapper(path, row):
        real_log_event_at(path, row)  # the genuine lifecycle_start write
        # A concurrent writer appends AFTER our row but BEFORE the verify read.
        real_log_event_at(
            path,
            {
                "event": "phase_transition",
                "feature": "feat",
                "from": "clarify",
                "to": "research",
            },
        )

    monkeypatch.setattr(refine_module, "log_event_at", _wrapper)

    rc = refine_module.main(["emit-lifecycle-start", "--lifecycle-slug", "feat"])
    assert rc == 0

    rows = _read_jsonl(_events_log_path(tmp_path, "feat"))
    # The seed is present but NOT the tail row — the tail is the concurrent row.
    assert rows[-1]["event"] == "phase_transition"
    assert any(r["event"] == "lifecycle_start" and r["feature"] == "feat" for r in rows)


# ---------------------------------------------------------------------------
# R11: backlog 227 regression scenario (simple-tier high-crit)
# ---------------------------------------------------------------------------


def test_emit_lifecycle_start_matches_227_repro_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R11: backlog #227 scenario — simple-tier high-crit propagates.

    After the helper runs, ``read_criticality(feat)`` returns ``"high"``
    and ``read_tier(feat)`` returns ``"simple"``. The canonical readers
    are ``@lru_cache``d; we clear the caches before reading to ensure a
    same-process emit-then-read sees the new file state.
    """
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "227-discovery-output-density",
        ["title: Foo", "criticality: high", "complexity: simple"],
    )

    rc = main(
        [
            "emit-lifecycle-start",
            "--backlog-slug",
            "227-discovery-output-density",
            "--lifecycle-slug",
            "feat-227",
        ]
    )
    assert rc == 0

    # Clear the canonical readers' lru_caches so the post-emit file state
    # is observed in-process (see plan.md Risks: lru_cache invalidation).
    # The wrapped inner function is the cached layer; the wrapper itself
    # is not cached but recomputes the (exists, mtime_ns, size) stat key
    # each call, so clearing the inner cache is sufficient.
    read_criticality.__wrapped__.cache_clear()  # type: ignore[attr-defined]
    read_tier.__wrapped__.cache_clear()  # type: ignore[attr-defined]

    lifecycle_base = tmp_path / "cortex" / "lifecycle"
    assert read_criticality("feat-227", lifecycle_base=lifecycle_base) == "high"
    assert read_tier("feat-227", lifecycle_base=lifecycle_base) == "simple"


# ===========================================================================
# reconcile-clarify (R1–R7) — appends override rows to reconcile events.log
# to the Clarify-determined tier/criticality.
# ===========================================================================


# ---------------------------------------------------------------------------
# R1-CtxA: Context-A backlog sourcing (the real production trigger)
# ---------------------------------------------------------------------------


def test_reconcile_clarify_sources_values_from_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-CtxA: desired values sourced from backlog frontmatter, no flags.

    This is the branch the headline bug fires through — a mis-wired
    ``_read_backlog_frontmatter`` call (wrong key/slug, complexity↔criticality
    swap) would pass every explicit-flag case but fail here.
    """
    monkeypatch.chdir(tmp_path)
    _write_backlog(
        tmp_path,
        "285-foo",
        ["title: Foo", "criticality: high", "complexity: complex"],
    )
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--backlog-slug",
            "285-foo",
        ]
    )
    assert rc == 0
    assert _reduce_events(events_log) == {"tier": "complex", "criticality": "high"}


# ---------------------------------------------------------------------------
# R1-Prec: explicit flags win over backlog frontmatter
# ---------------------------------------------------------------------------


def test_reconcile_clarify_flags_take_precedence_over_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-Prec: when both flags and ``--backlog-slug`` are passed, flags win."""
    monkeypatch.chdir(tmp_path)
    # Backlog says complex/critical; explicit flags say complex/high.
    _write_backlog(
        tmp_path,
        "285-foo",
        ["title: Foo", "criticality: critical", "complexity: complex"],
    )
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--backlog-slug",
            "285-foo",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0
    # Flags (high) win over backlog (critical).
    assert _reduce_events(events_log) == {"tier": "complex", "criticality": "high"}


# ---------------------------------------------------------------------------
# R1: reduce-agreement
# ---------------------------------------------------------------------------


def test_reconcile_clarify_reduce_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1: seed simple/medium, reconcile complex/high → reduce agrees."""
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0
    assert _reduce_events(events_log) == {"tier": "complex", "criticality": "high"}


# ---------------------------------------------------------------------------
# R2: both canonical readers agree with the reduce
# ---------------------------------------------------------------------------


def test_reconcile_clarify_both_readers_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: after reconcile, common.py readers equal the state_cli reduce.

    Pins that a ``to``-keyed override row is read identically by both
    ``common.py`` (reads ``.to`` only) and ``state_cli`` (reads
    ``.to or .criticality``/``.to or .tier``).
    """
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0

    # Clear the lru_caches so the post-write file state is observed in-process.
    read_criticality.__wrapped__.cache_clear()  # type: ignore[attr-defined]
    read_tier.__wrapped__.cache_clear()  # type: ignore[attr-defined]

    reduced = _reduce_events(events_log)
    lifecycle_base = tmp_path / "cortex" / "lifecycle"
    assert read_tier("feat", lifecycle_base=lifecycle_base) == reduced["tier"] == "complex"
    assert (
        read_criticality("feat", lifecycle_base=lifecycle_base)
        == reduced["criticality"]
        == "high"
    )


# ---------------------------------------------------------------------------
# R3: idempotency — second identical invocation appends nothing
# ---------------------------------------------------------------------------


def test_reconcile_clarify_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3: invoke twice with the same values → override counts unchanged."""
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    argv = [
        "reconcile-clarify",
        "--lifecycle-slug",
        "feat",
        "--complexity",
        "complex",
        "--criticality",
        "high",
    ]
    assert main(argv) == 0
    size_after_first = events_log.stat().st_size
    complexity_after_first = _count_event(events_log, "complexity_override")
    criticality_after_first = _count_event(events_log, "criticality_override")

    assert main(argv) == 0
    assert events_log.stat().st_size == size_after_first
    assert _count_event(events_log, "complexity_override") == complexity_after_first == 1
    assert (
        _count_event(events_log, "criticality_override") == criticality_after_first == 1
    )


# ---------------------------------------------------------------------------
# R4: no-downgrade — a lower desired value never lowers the state
# ---------------------------------------------------------------------------


def test_reconcile_clarify_no_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R4: reduced state already complex/high; reconcile simple/medium no-ops."""
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(
        tmp_path, "feat", [_lifecycle_start_line("complex", "high")]
    )
    before = events_log.read_text(encoding="utf-8")

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "simple",
            "--criticality",
            "medium",
        ]
    )
    assert rc == 0
    # No override row appended; state unchanged.
    assert events_log.read_text(encoding="utf-8") == before
    assert _count_event(events_log, "complexity_override") == 0
    assert _count_event(events_log, "criticality_override") == 0
    assert _reduce_events(events_log) == {"tier": "complex", "criticality": "high"}


# ---------------------------------------------------------------------------
# R5: malformed-line tolerance — a torn line does not collapse the reduce
# ---------------------------------------------------------------------------


def test_reconcile_clarify_tolerates_malformed_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5: a malformed line alongside a valid seed → exit 0, overrides appended.

    The shared tolerant reducer skips the torn line and still reads the valid
    seed's simple/medium, so the complex/high reconciliation proceeds. (All
    three readers — ``state_cli``, ``read_tier``/``read_criticality``, and
    ``refine._reduce_current_state`` — share ``reduce_lifecycle_state`` and so
    agree on the torn log; see plan Risks / #287.)
    """
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(
        tmp_path,
        "feat",
        [_lifecycle_start_line(), "this is not valid json {{{"],
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0
    assert _count_event(events_log, "complexity_override") == 1
    assert _count_event(events_log, "criticality_override") == 1


# ---------------------------------------------------------------------------
# R6: append-only — the original lifecycle_start line is preserved verbatim
# ---------------------------------------------------------------------------


def test_reconcile_clarify_append_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6: the seed ``lifecycle_start`` line is byte-identical after reconcile."""
    monkeypatch.chdir(tmp_path)
    seed_line = _lifecycle_start_line()
    events_log = _seed_events(tmp_path, "feat", [seed_line])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0
    lines = events_log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == seed_line


# ---------------------------------------------------------------------------
# R7: provenance — every appended override carries gate: clarify_reconcile
# ---------------------------------------------------------------------------


def test_reconcile_clarify_provenance_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7: ``gate: clarify_reconcile`` count equals fields reconciled (2)."""
    monkeypatch.chdir(tmp_path)
    events_log = _seed_events(tmp_path, "feat", [_lifecycle_start_line()])

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            "feat",
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0
    gate_count = sum(
        1 for row in _read_jsonl(events_log) if row.get("gate") == "clarify_reconcile"
    )
    assert gate_count == 2  # both tier and criticality reconciled


# ---------------------------------------------------------------------------
# #322 Phase 2: --backend structural guard
#
# On a non-local backend a passed --backlog-slug is ignored (no local file is
# read) and a stderr diagnostic is emitted; a trailing-whitespace
# 'cortex-backlog' value is stripped and treated as local. The default arm
# stays byte-identical, verified against a hand-written contract literal (NOT
# captured from the production serializer) with ts masked via a raw-string
# regex substitution so a key-order/separator regression cannot be normalized
# away.
# ---------------------------------------------------------------------------


def _mask_ts(line: str) -> str:
    """Mask the non-deterministic ts via raw-string substitution on the bytes.

    Deliberately NOT a json.loads -> json.dumps round-trip: a round-trip would
    re-serialize the production line with this test's separators and normalize
    away the exact key-order/separator regression the literal exists to catch.
    """
    return re.sub(r'"ts": "[^"]*"', '"ts": "<TS>"', line.strip())


def test_backend_guard_emit_ignores_stale_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    # A stale local backlog file with non-default values sits on disk.
    _write_backlog(tmp_path, "X", ["complexity: complex", "criticality: high"])

    rc = main(
        [
            "emit-lifecycle-start",
            "--backend",
            "github",
            "--backlog-slug",
            "X",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    seed = _read_jsonl(_events_log_path(tmp_path, "feat"))[0]
    # The stale X.md (complex/high) was NOT read — seed carries the defaults.
    assert seed["tier"] == "simple"
    assert seed["criticality"] == "medium"

    err = capsys.readouterr().err
    assert "ignoring --backlog-slug" in err
    assert "github" in err


def test_backend_guard_reconcile_ignores_stale_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_backlog(tmp_path, "X", ["complexity: complex", "criticality: high"])
    _seed_events(tmp_path, "feat", [_lifecycle_start_line("simple", "medium")])

    # Non-local backend + stale slug, no explicit flags. If the file were read,
    # reconcile would ratchet to complex/high; the guard drops the slug, so the
    # reduced state stays at the seed defaults and no override is appended.
    rc = main(
        [
            "reconcile-clarify",
            "--backend",
            "github",
            "--backlog-slug",
            "X",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    events_log = _events_log_path(tmp_path, "feat")
    assert _reduce_events(events_log) == {"tier": "simple", "criticality": "medium"}
    assert _count_event(events_log, "complexity_override") == 0
    assert _count_event(events_log, "criticality_override") == 0

    err = capsys.readouterr().err
    assert "ignoring --backlog-slug" in err
    assert "github" in err


def test_backend_guard_trailing_whitespace_treated_as_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_backlog(tmp_path, "X", ["complexity: complex", "criticality: high"])

    # A trailing newline (as a piped `cortex-read-backlog-backend` would yield)
    # is stripped, so the value is treated as the local cortex-backlog arm.
    rc = main(
        [
            "emit-lifecycle-start",
            "--backend",
            "cortex-backlog\n",
            "--backlog-slug",
            "X",
            "--lifecycle-slug",
            "feat",
        ]
    )
    assert rc == 0

    seed = _read_jsonl(_events_log_path(tmp_path, "feat"))[0]
    # Treated as local → X.md WAS read.
    assert seed["tier"] == "complex"
    assert seed["criticality"] == "high"
    assert capsys.readouterr().err == ""


def test_emit_row_byte_identical_to_hardcoded_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hand-written contract literal pinning key ORDER + SEPARATORS. NOT captured
    # from the production serializer — a regression in either fails this assert.
    # Since #374 the row is written through the shared locked primitive
    # (``lifecycle_event.log_event_at``), which prepends the ``ts`` base key, so
    # the canonical order is now ``ts`` first, then the seed's ``schema_version``
    # and remaining fields (semantics preserved; consumers key by name).
    expected = (
        '{"ts": "<TS>", "schema_version": 1, "event": "lifecycle_start", '
        '"feature": "feat", "tier": "simple", "criticality": "medium", '
        '"entry_point": "refine"}'
    )
    for i, backend_args in enumerate([[], ["--backend", "cortex-backlog"]]):
        workdir = tmp_path / f"run{i}"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        rc = main(
            ["emit-lifecycle-start", "--lifecycle-slug", "feat", *backend_args]
        )
        assert rc == 0

        line = _events_log_path(workdir, "feat").read_text().strip()
        assert _mask_ts(line) == expected


def test_reconcile_override_row_byte_identical_to_hardcoded_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hand-written contract literal for the override row (the OTHER verb gaining
    # --backend), pinning its key order + separators per spec R7 ("each verb").
    expected = (
        '{"ts": "<TS>", "event": "complexity_override", "feature": "feat", '
        '"from": "simple", "to": "complex", "gate": "clarify_reconcile"}'
    )
    for i, backend_args in enumerate([[], ["--backend", "cortex-backlog"]]):
        workdir = tmp_path / f"run{i}"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        _seed_events(workdir, "feat", [_lifecycle_start_line("simple", "medium")])

        rc = main(
            [
                "reconcile-clarify",
                "--lifecycle-slug",
                "feat",
                "--complexity",
                "complex",
                *backend_args,
            ]
        )
        assert rc == 0

        overrides = [
            ln
            for ln in _events_log_path(workdir, "feat").read_text().splitlines()
            if '"complexity_override"' in ln
        ]
        assert len(overrides) == 1
        assert _mask_ts(overrides[0]) == expected
