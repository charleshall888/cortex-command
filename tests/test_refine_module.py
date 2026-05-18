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
