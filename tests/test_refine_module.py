"""Unit tests for ``cortex_command.refine`` (spec R1, R2, R3, R5, R11).

Covers the ``emit-lifecycle-start`` subcommand:

  - R1: ``test_emit_lifecycle_start_writes_backlog_values`` — backlog
    ``criticality: high`` + ``complexity: complex`` → row matches.
  - R2: ``test_emit_lifecycle_start_defaults`` — parametrized over
    missing criticality, missing complexity, no backlog file.
  - R3: ``test_emit_lifecycle_start_idempotent`` — pre-seeded events.log
    with a ``lifecycle_start`` row → second invocation no-ops.
  - R5: ``test_emit_lifecycle_start_rejects_invalid_value`` —
    parametrized over ``criticality: extreme`` and ``complexity: medium``
    (wrong dimension).
  - R11: ``test_emit_lifecycle_start_matches_227_repro_scenario`` —
    backlog with ``criticality: high`` + ``complexity: simple`` →
    ``read_criticality`` returns ``"high"`` and ``read_tier`` returns
    ``"simple"``.

Tests call ``main`` directly with ``monkeypatch.chdir(tmp_path)`` to
isolate the working directory.
"""

from __future__ import annotations

import json
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
            "complexity_medium_wrong_dimension",
            ["title: Foo", "criticality: high", "complexity: medium"],
            "medium",
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

    The local tolerant reduce skips the torn line and still reads the valid
    seed's simple/medium, so the complex/high reconciliation proceeds. (This
    diverges from ``state_cli._reduce_events``, which would null on the torn
    line — see plan Risks / #287.)
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
