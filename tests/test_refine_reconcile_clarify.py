"""End-to-end + delegated-path tests for `cortex-refine reconcile-clarify`.

Two scenarios, both driven through the production data-flow rather than a
shortcut:

  - R12 standalone (headline bug): a fresh ticket whose backlog frontmatter
    Clarify assessed `complex/high`, seeded with a `simple/medium`
    `lifecycle_start` row before Clarify ran. After reconcile-clarify (Context
    A — values sourced from the backlog, NO explicit flags), the
    `cortex-lifecycle-state` CLI surface reports `complex`/`high`, so the §3b
    critical-review gate fires instead of silently skipping.

  - R12 delegated: under `/cortex-core:build`, lifecycle logs a corrected
    post-Clarify `lifecycle_start(complex/high)` before Research. reconcile-
    clarify must then no-op (the state-based no-op guard suppresses it because
    the reduced state already reads complex/high — NOT via supersession), so
    no duplicate override row is appended.

Live `cortex-refine` reads the installed wheel; these tests call `main([...])`
in-process so they exercise the source without a wheel reinstall.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cortex_command import refine as refine_mod
from cortex_command.lifecycle import state_cli
from cortex_command.lifecycle.state_cli import _reduce_events
from cortex_command.refine import main

# Canonical sources whose non-local refine branch carries the explicit-flag
# reconcile invocation. Read from the repo root (two parents up from tests/).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REFINE_SKILL = _REPO_ROOT / "skills" / "refine" / "SKILL.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _events_log_path(tmp_path: Path, lifecycle_slug: str) -> Path:
    return tmp_path / "cortex" / "lifecycle" / lifecycle_slug / "events.log"


def _lifecycle_start_line(feature: str, tier: str, criticality: str) -> str:
    return json.dumps(
        {
            "schema_version": 3,
            "ts": "2026-01-01T00:00:00Z",
            "event": "lifecycle_start",
            "feature": feature,
            "tier": tier,
            "criticality": criticality,
            "entry_point": "refine",
        }
    )


def _seed_events(tmp_path: Path, lifecycle_slug: str, lines: list[str]) -> Path:
    events_log = _events_log_path(tmp_path, lifecycle_slug)
    events_log.parent.mkdir(parents=True, exist_ok=True)
    events_log.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return events_log


def _write_backlog(
    tmp_path: Path, slug: str, complexity: str, criticality: str
) -> None:
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        f"title: Fixture {slug}\n"
        f"complexity: {complexity}\n"
        f"criticality: {criticality}\n"
        "---\n\n# Body\n"
    )
    (backlog_dir / f"{slug}.md").write_text(fm, encoding="utf-8")


def _count_overrides(events_log: Path) -> int:
    count = 0
    for line in events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event") in (
            "complexity_override",
            "criticality_override",
        ):
            count += 1
    return count


def _override_rows(events_log: Path) -> list[dict]:
    """Every override row in the log, in append order.

    Distinct from :func:`_count_overrides`: the reason tests assert on the row
    *shape* (which keys are present, and in what order), so a count is not
    enough — a missing-`reason` assertion made against the whole file's text
    would also pass if no row had been appended at all.
    """
    rows: list[dict] = []
    for line in events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event") in (
            "complexity_override",
            "criticality_override",
        ):
            rows.append(row)
    return rows


def _only(rows: list[dict], event: str) -> dict:
    matches = [r for r in rows if r.get("event") == event]
    assert len(matches) == 1, f"expected exactly one {event} row, got {len(matches)}"
    return matches[0]


def _state_field(
    capsys: pytest.CaptureFixture[str], feature: str, field: str
) -> dict:
    """Invoke the cortex-lifecycle-state CLI surface and parse its JSON stdout.

    ``state_cli.main`` ends with ``sys.exit(0)`` on success, so we absorb the
    SystemExit and assert it was a clean exit.
    """
    with pytest.raises(SystemExit) as exc_info:
        state_cli.main(["--feature", feature, "--field", field])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out.strip()
    return json.loads(out)


# ---------------------------------------------------------------------------
# R12 standalone: the headline bug, reproduced via the Clarify→backlog→reconcile
# data-flow (Context A), verified through the cortex-lifecycle-state CLI surface.
# ---------------------------------------------------------------------------


def test_reconcile_clarify_standalone_headline_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    slug = "285-standalone-refine"
    feature = "standalone-refine"

    # Clarify wrote back complex/high to the backlog; events.log still carries
    # the pre-Clarify simple/medium seed.
    _write_backlog(tmp_path, slug, complexity="complex", criticality="high")
    _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    # Context A: no explicit flags — values sourced from the backlog file.
    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--backlog-slug",
            slug,
        ]
    )
    assert rc == 0

    # The verb reports what it did, so the caller can route without a second
    # cortex-lifecycle-state round-trip.
    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"
    assert envelope["rows"] == 2
    assert envelope["tier"] == "complex"
    assert envelope["criticality"] == "high"
    assert {o["field"] for o in envelope["overrides"]} == {
        "complexity_override",
        "criticality_override",
    }

    # The §3b read surface (cortex-lifecycle-state) now reports the Clarify values.
    assert _state_field(capsys, feature, "tier") == {"tier": "complex"}
    assert _state_field(capsys, feature, "criticality") == {"criticality": "high"}


# ---------------------------------------------------------------------------
# R12 delegated: lifecycle's post-Clarify lifecycle_start already moved the
# reduced state, so reconcile-clarify no-ops (no duplicate override row).
# ---------------------------------------------------------------------------


def test_reconcile_clarify_delegated_path_noops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    feature = "delegated-feat"

    # Under /cortex-core:build, the corrected post-Clarify lifecycle_start
    # (complex/high) is logged before Research — moving the reduced state.
    events_log = _seed_events(
        tmp_path,
        feature,
        [
            _lifecycle_start_line(feature, "simple", "medium"),
            _lifecycle_start_line(feature, "complex", "high"),
        ],
    )
    overrides_before = _count_overrides(events_log)
    assert overrides_before == 0

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0

    # No-op guard: no override row appended (suppressed because the reduced
    # state already reads complex/high — not via supersession).
    assert _count_overrides(events_log) == overrides_before == 0
    assert _reduce_events(events_log) == {"tier": "complex", "criticality": "high"}

    # The no-op is REPORTED, not silent. Previously this arm and the ratcheted
    # arm both printed nothing, so the caller could not tell "already
    # reconciled" from "ratcheted" from "suppressed a downgrade" without a
    # second cortex-lifecycle-state read. `noop` is legitimate on resume and
    # must not read as an error: rc is still 0.
    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "noop"
    assert envelope["rows"] == 0
    assert envelope["tier"] == "complex"
    assert envelope["criticality"] == "high"


def test_reconcile_clarify_reports_noop_when_a_downgrade_is_suppressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A suppressed downgrade reports `noop` at the value that survived.

    The monotonic no-downgrade guard is silent by design; reporting the state
    it left behind is what lets the caller see that its requested value did not
    win, rather than assuming it did.
    """
    monkeypatch.chdir(tmp_path)
    feature = "downgrade-feat"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "complex", "high")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "simple",
            "--criticality",
            "low",
        ]
    )
    assert rc == 0
    assert _count_overrides(events_log) == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "noop"
    assert envelope["rows"] == 0
    # The surviving (not the requested) values.
    assert envelope["tier"] == "complex"
    assert envelope["criticality"] == "high"


# ---------------------------------------------------------------------------
# R8 functional regression (#317): under a non-local backend, the refine arm
# omits --backlog-slug and feeds Clarify's computed tier/criticality forward as
# explicit flags. reconcile-clarify must ratchet the seed defaults up so the
# §3b read surface (cortex-lifecycle-state) reports the Clarify values, keeping
# the critical-review gate alive. No --backlog-slug → no local file read.
# ---------------------------------------------------------------------------


def test_reconcile_clarify_non_local_explicit_flags_ratchets_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    feature = "non-local-refine"

    # Non-local seed: emit-lifecycle-start omitted --backlog-slug, so the seed
    # carries the simple/medium defaults (no local backlog file is created).
    _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    # Non-local Context-B reconcile: no --backlog-slug, Clarify's computed
    # tier/criticality passed as explicit flags.
    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"
    assert envelope["rows"] == 2

    # The §3b read surface now reports the ratcheted Clarify values, so the
    # critical-review gate fires instead of skipping silently at simple.
    assert _state_field(capsys, feature, "tier") == {"tier": "complex"}
    assert _state_field(capsys, feature, "criticality") == {"criticality": "high"}


# ---------------------------------------------------------------------------
# R8 structural (#322 one-call shape): the backend-keyed two-arm prose is gone
# — both verbs lead with --backend {resolved} and the verb's guard owns the
# non-local slug-drop. The item-existence (Context A/B) distinction is still
# POSITIVELY pinned (Context A passes the backlog slug; Context B passes the
# computed {value} tier/criticality), and the value-aware #285/#317 negative
# control (no seed-default literals) is preserved.
# ---------------------------------------------------------------------------


def test_refine_non_local_reconcile_branch_is_value_aware() -> None:
    body = _REFINE_SKILL.read_text(encoding="utf-8")

    # One-call shape: reconcile leads with --backend {resolved}. The seed's own
    # --backend threading moved inside `cortex-refine start`, which resolves the
    # backend itself, so the skill body no longer spells that flag for the seed.
    assert "cortex-refine start" in body
    assert "reconcile-clarify --backend {resolved}" in body

    # Positive contiguous-shape pins for the item-existence invariant. Context A
    # still passes the backlog slug; Context B still passes the computed {value}
    # tier/criticality. A collapse that dropped either flag set would fail here,
    # so the invariant is positively guarded — not only negatively.
    assert (
        "reconcile-clarify --backend {resolved} --lifecycle-slug "
        "{lifecycle-slug} --backlog-slug {backlog-filename-slug}" in body
    )
    assert (
        "reconcile-clarify --backend {resolved} --lifecycle-slug "
        "{lifecycle-slug} --complexity {value} --criticality {value}" in body
    )

    # Value-aware negative control (#285/#317): the reconcile invocation must
    # NOT hardcode the seed defaults — no `--complexity simple` /
    # `--criticality medium` literal form.
    assert not re.search(r"reconcile-clarify[^\n]*--complexity\s+simple", body)
    assert not re.search(r"reconcile-clarify[^\n]*--criticality\s+medium", body)

    # Routing stays keyed on a RESOLVED backend rather than a static branch.
    # The standalone `cortex-read-backlog-backend` call folded into
    # `cortex-refine start`, which resolves and returns it, so the body pins
    # the resolved value's threading instead of the resolver invocation.
    assert "{resolved}" in body
    assert "`backend`" in body, (
        "refine SKILL.md must name the backend field the start verb returns, "
        "so downstream write-backs key on it"
    )
    assert refine_mod.resolve_backlog_backend is not None, (
        "cortex-refine no longer imports the backend resolver; `start` would "
        "return a static backend"
    )


# ---------------------------------------------------------------------------
# Clause-tagged override reasons: the criticality axis is only auditable if the
# reasoning Clarify already computed has a destination on the row a corpus
# count reads. The reason is per-axis and optional, and an unknown clause tag
# must be rejected *before* anything is appended (R4/R5/R6).
# ---------------------------------------------------------------------------


def test_reconcile_clarify_records_criticality_reason_per_axis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reason lands on its own axis only, at the pinned key position.

    Both axes ratchet in this one call, but only ``--criticality-reason`` is
    supplied — so the criticality row carries the reason and the complexity row
    must not inherit it. The key order is pinned because matching the field
    order ``lifecycle_event.py`` declares for the typed override verbs (from,
    to, reason) across both writers is the point of placing it there.
    """
    monkeypatch.chdir(tmp_path)
    feature = "reason-per-axis"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
            "--criticality-reason",
            "exposure: shared skill prose",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"
    assert envelope["rows"] == 2

    rows = _override_rows(events_log)
    assert len(rows) == 2

    crit = _only(rows, "criticality_override")
    assert crit["reason"] == "exposure: shared skill prose"
    assert list(crit.keys()) == [
        "ts",
        "event",
        "feature",
        "from",
        "to",
        "reason",
        "gate",
    ]

    # Per-axis independence: the untagged axis stays byte-identical in shape to
    # a pre-reason override row.
    tier = _only(rows, "complexity_override")
    assert "reason" not in tier
    assert list(tier.keys()) == ["ts", "event", "feature", "from", "to", "gate"]


def test_reconcile_clarify_rejects_out_of_set_clause_tag_without_appending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown clause tag exits 2 and leaves the log byte-identical.

    Asserted on the file's bytes rather than a row count: validation runs before
    the rows are built, so a partial append (tier written, criticality rejected)
    is exactly the failure this pins against. The exit code is pinned to the
    specific value 2 rather than "non-zero" so that a crash in the verb — which
    would also append nothing — cannot satisfy this test.
    """
    monkeypatch.chdir(tmp_path)
    feature = "reason-bad-tag"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )
    before = events_log.read_bytes()

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
            "--criticality-reason",
            "bogus: x",
        ]
    )
    assert rc == 2
    assert events_log.read_bytes() == before

    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    assert "bogus" in captured.err


def test_reconcile_clarify_without_reason_flags_omits_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omission drops the key entirely rather than writing a null.

    Asserted positively — the override rows must actually have been appended,
    with the right ``from``/``to`` — because "the string `reason` does not
    appear in this file" is also true of a verb that never ran.
    """
    monkeypatch.chdir(tmp_path)
    feature = "reason-omitted"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"
    assert envelope["rows"] == 2

    rows = _override_rows(events_log)
    crit = _only(rows, "criticality_override")
    assert (crit["from"], crit["to"]) == ("medium", "high")
    assert "reason" not in crit

    tier = _only(rows, "complexity_override")
    assert (tier["from"], tier["to"]) == ("simple", "complex")
    assert "reason" not in tier


def test_reconcile_clarify_accepts_untagged_reason_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No colon → nothing is parsed as a clause, so the text is recorded as-is."""
    monkeypatch.chdir(tmp_path)
    feature = "reason-untagged"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--criticality",
            "high",
            "--criticality-reason",
            "plain text",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"

    crit = _only(_override_rows(events_log), "criticality_override")
    assert crit["reason"] == "plain text"


def test_reconcile_clarify_accepts_a_colon_inside_the_reason_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the text before the FIRST colon is the clause tag.

    A valid tag whose body itself contains a colon must still be accepted and
    stored verbatim — a naive "reject any reason with more than one colon" would
    fail here, and a naive split on every colon would store a truncated reason.
    """
    monkeypatch.chdir(tmp_path)
    feature = "reason-inner-colon"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )
    reason = "exposure: consumed by overnight/: runner"

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--criticality",
            "high",
            "--criticality-reason",
            reason,
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"

    crit = _only(_override_rows(events_log), "criticality_override")
    assert crit["reason"] == reason


def test_reconcile_clarify_records_tier_reason_per_axis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A supplied ``--tier-reason`` lands on the complexity row and only there.

    The mirror image of the criticality case: both axes ratchet, only the tier
    reason is supplied. This is the surface's only consumer-side proof — without
    it the tier axis of the reason feature has no test at all, so a deletion of
    the ``--tier-reason`` argparse block would leave the suite green.
    """
    monkeypatch.chdir(tmp_path)
    feature = "tier-reason-per-axis"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
            "--tier-reason",
            "consequence: touches every refine route",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"
    assert envelope["rows"] == 2

    rows = _override_rows(events_log)
    assert len(rows) == 2

    tier = _only(rows, "complexity_override")
    assert tier["reason"] == "consequence: touches every refine route"
    assert list(tier.keys()) == [
        "ts",
        "event",
        "feature",
        "from",
        "to",
        "reason",
        "gate",
    ]

    # Per-axis independence in the other direction: the untagged criticality
    # row must not inherit the tier's reason.
    crit = _only(rows, "criticality_override")
    assert "reason" not in crit
    assert list(crit.keys()) == ["ts", "event", "feature", "from", "to", "gate"]


def test_reconcile_clarify_empty_tier_reason_omits_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--tier-reason ""`` still ratchets, but writes no ``reason`` key.

    An empty string is not an axis a corpus tally can bucket on, so it is
    dropped exactly as an omitted flag is — not recorded as ``"reason": ""``.
    Asserted positively on ``from``/``to`` because "no reason key in this file"
    is also true of a verb that appended nothing.
    """
    monkeypatch.chdir(tmp_path)
    feature = "tier-reason-empty"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--tier-reason",
            "",
        ]
    )
    assert rc == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ratcheted"

    tier = _only(_override_rows(events_log), "complexity_override")
    assert (tier["from"], tier["to"]) == ("simple", "complex")
    assert "reason" not in tier
    assert list(tier.keys()) == ["ts", "event", "feature", "from", "to", "gate"]


def test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two bad tags produce two diagnostics, not one per re-run.

    Validation of the two axes runs unconditionally rather than short-circuiting
    on the first failure, so a caller that got both tags wrong learns both at
    once. Each message is matched together with its own bogus tag, so a single
    diagnostic printed twice cannot satisfy this.
    """
    monkeypatch.chdir(tmp_path)
    feature = "both-bad-tags"
    events_log = _seed_events(
        tmp_path, feature, [_lifecycle_start_line(feature, "simple", "medium")]
    )
    before = events_log.read_bytes()

    rc = main(
        [
            "reconcile-clarify",
            "--lifecycle-slug",
            feature,
            "--complexity",
            "complex",
            "--criticality",
            "high",
            "--tier-reason",
            "tierbogus: x",
            "--criticality-reason",
            "critbogus: y",
        ]
    )
    assert rc == 2
    assert events_log.read_bytes() == before

    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    err_lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(err_lines) == 2
    assert any(
        "--tier-reason" in line and "tierbogus" in line for line in err_lines
    ), captured.err
    assert any(
        "--criticality-reason" in line and "critbogus" in line for line in err_lines
    ), captured.err


def test_refine_skill_passes_the_tier_reason_flag() -> None:
    """refine SKILL.md must spell ``--tier-reason`` on its reconcile calls.

    Bare existence, because the omission fails silently: Clarify's tier
    reasoning simply never reaches a ``complexity_override`` row, every such row
    reads ``simple -> complex`` with no recorded why, and nothing — no exit
    code, no diagnostic, no failing gate — surfaces that the reason was never
    recorded. Only a corpus tally months later would show the gap.
    """
    body = _REFINE_SKILL.read_text(encoding="utf-8")
    assert "--tier-reason" in body
