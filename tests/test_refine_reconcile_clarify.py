"""End-to-end + delegated-path tests for `cortex-refine reconcile-clarify`.

Two scenarios, both driven through the production data-flow rather than a
shortcut:

  - R12 standalone (headline bug): a fresh ticket whose backlog frontmatter
    Clarify assessed `complex/high`, seeded with a `simple/medium`
    `lifecycle_start` row before Clarify ran. After reconcile-clarify (Context
    A — values sourced from the backlog, NO explicit flags), the
    `cortex-lifecycle-state` CLI surface reports `complex`/`high`, so the §3b
    critical-review gate fires instead of silently skipping.

  - R12 delegated: under `/cortex-core:lifecycle`, lifecycle logs a corrected
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

    # The §3b read surface (cortex-lifecycle-state) now reports the Clarify values.
    assert _state_field(capsys, feature, "tier") == {"tier": "complex"}
    assert _state_field(capsys, feature, "criticality") == {"criticality": "high"}


# ---------------------------------------------------------------------------
# R12 delegated: lifecycle's post-Clarify lifecycle_start already moved the
# reduced state, so reconcile-clarify no-ops (no duplicate override row).
# ---------------------------------------------------------------------------


def test_reconcile_clarify_delegated_path_noops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    feature = "delegated-feat"

    # Under /cortex-core:lifecycle, the corrected post-Clarify lifecycle_start
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

    # One-call shape: both verbs now lead with --backend {resolved}.
    assert "emit-lifecycle-start --backend {resolved}" in body
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

    # The backend resolver is referenced so routing is keyed on the resolved
    # backend, not a static branch.
    assert "cortex-read-backlog-backend" in body
