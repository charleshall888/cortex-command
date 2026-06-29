"""Call-site-pinned round-trip tests for the lifecycle-event migration (#330, R11).

Two independent arms per migrated event:

(i) GOLDEN — run the event's canonical typed argv through the verb
    (``cortex_command.lifecycle_event._run``) in a ``tmp_path`` root with
    ``_now_iso`` monkeypatched, and assert the appended line equals an inline
    golden byte string. This pins serialization (spaced ``json.dumps`` +
    ``Z`` timestamp), key order, and — critically — JSON TYPES:
    ``batch_dispatch``'s numeric ``batch`` / array ``tasks`` and
    ``review_verdict``'s numeric ``cycle`` / ``drift_protocol_breach``'s
    numeric ``retries`` are JSON numbers/arrays, while string fields stay
    quoted. For ``feature_complete`` the golden also asserts the line contains
    the exact ``"event": "feature_complete"`` substring — the ``needle_tight``
    literal ``cortex_command/hooks/scan_lifecycle.py`` string-matches.

(ii) ON-DISK CROSS-VALIDATION — parse EVERY ``cortex-lifecycle-event log
    --event X ...`` invocation out of each migrated ``.md`` (tolerating
    fenced ```` ```bash ```` blocks and placeholder values like ``from=<...>``
    or ``tasks=[<task IDs>]`` — the flag-kind and field-KEY are concrete even
    when the value is a placeholder), and for EACH invocation assert its
    (field-key set, per-field flag-kind) matches the canonical for that event.
    A fail-loud found-match check asserts the parser located exactly the
    expected number of invocations per (file, event), so a parse that finds
    zero/too-few/too-many fails rather than passing an empty loop.

**Residual limitation (documented, not closed):** the canonical argv is
author-supplied, so arm (ii) detects on-disk DRIFT FROM the canonical, not a
canonical that is itself wrong in lockstep with the ``.md``. Arm (i)'s golden
is the independent type/spacing anchor. The label is "flag-and-field-set
cross-validation," not full value-pinning (the ``.md`` values are placeholders).

``phase_transition`` is NON-UNIFORM across sites: most rows carry ``{from,to}``,
but ``implement.md`` §4 legitimately carries ``{tier,from,to}``. The canonical
allows both key sets for that event (and only that event).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cortex_command import lifecycle_event
from cortex_command.lifecycle_event import _run


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXED_TS = "2026-06-29T12:00:00Z"


# ---------------------------------------------------------------------------
# Helpers — cortex root setup + invocation parsing
# ---------------------------------------------------------------------------


def _setup_cortex_root(base: Path) -> Path:
    """Create a minimal cortex project tree under *base* and return it."""
    (base / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    return base


_EVENT_RE = re.compile(
    r"cortex-lifecycle-event\s+log\b.*?--event[ =]([a-z_][a-z0-9_]*)"
)
_FIELD_RE = re.compile(r"--set(-json)?\s+([a-z_][a-z0-9_]*)=")


class CrossValidationError(Exception):
    """Raised when an on-disk invocation drifts from the canonical contract."""


def parse_invocations(path: Path) -> list[tuple[int, str, dict[str, str]]]:
    """Return ``[(lineno, event_name, {field_key: flag_kind}), ...]``.

    ``flag_kind`` is ``"set"`` (``--set``, literal string) or ``"json"``
    (``--set-json``). Only the flag-kind and field-key are extracted — the
    value (often a placeholder) is intentionally ignored.
    """
    out: list[tuple[int, str, dict[str, str]]] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "cortex-lifecycle-event" not in line or "--event" not in line:
            continue
        m = _EVENT_RE.search(line)
        if not m:
            continue
        field_map: dict[str, str] = {}
        for suffix, key in _FIELD_RE.findall(line):
            field_map[key] = "json" if suffix == "-json" else "set"
        out.append((lineno, m.group(1), field_map))
    return out


# Canonical field-map(s) per event: event -> list of allowed {key: flag_kind}.
# A list with one entry means the event is uniform; ``phase_transition`` has
# two allowed key sets (the implement.md §4 row carries a preserved ``tier``).
CANONICAL: dict[str, list[dict[str, str]]] = {
    "plan_approved": [{"dispatch_choice": "set"}],
    "feature_paused": [{}],
    "phase_transition": [
        {"from": "set", "to": "set"},
        {"tier": "set", "from": "set", "to": "set"},
    ],
    "review_verdict": [
        {"verdict": "set", "cycle": "json", "requirements_drift": "set"}
    ],
    "drift_protocol_breach": [
        {"state": "set", "suggestion": "set", "retries": "json"}
    ],
    "batch_dispatch": [{"batch": "json", "tasks": "json"}],
    "criticality_override": [{"from": "set", "to": "set"}],
    "lifecycle_critical_review_skipped": [
        {"phase": "set", "tier": "set", "criticality": "set"}
    ],
    "lifecycle_start": [{"tier": "set", "criticality": "set"}],
    "spec_approved": [{}],
    "feature_complete": [{}],
}

# Per-file expected invocation counts for each migrated event (the Task 5-9
# on-disk reality). ``implement.md`` also carries an ``interactive_worktree_
# entered`` line (Task 1) — out of #330's migration scope — which is not in any
# entry here, so it is never cross-validated by these counts.
FILE_EVENTS: dict[str, dict[str, int]] = {
    "skills/lifecycle/references/plan.md": {
        "plan_approved": 2,
        "feature_paused": 1,
        "phase_transition": 1,
    },
    "skills/lifecycle/references/review.md": {
        "review_verdict": 1,
        "drift_protocol_breach": 1,
        "phase_transition": 3,
    },
    "skills/lifecycle/references/implement.md": {
        "batch_dispatch": 1,
        "phase_transition": 2,
    },
    "skills/refine/references/specify.md": {
        "spec_approved": 1,
        "phase_transition": 1,
    },
    "skills/lifecycle/references/criticality-matrix.md": {
        "criticality_override": 1,
    },
    "skills/lifecycle/references/critical-review-gate.md": {
        "lifecycle_critical_review_skipped": 1,
    },
    "skills/lifecycle/references/backlog-writeback.md": {
        "feature_complete": 1,
    },
    "skills/lifecycle/references/refine-delegation.md": {
        "lifecycle_start": 1,
        "phase_transition": 1,
    },
}


def cross_validate(path: Path, event: str, expected_count: int) -> None:
    """Fail loud if *event*'s on-disk invocations drift from the canonical.

    Raises ``CrossValidationError`` when the found count != *expected_count*
    (anti-vacuous), or when any matching invocation's field-key set / per-field
    flag-kind is not an allowed canonical for *event*.
    """
    matching = [fm for (_ln, ev, fm) in parse_invocations(path) if ev == event]
    if len(matching) != expected_count:
        raise CrossValidationError(
            f"{path}: expected {expected_count} '{event}' invocation(s), "
            f"found {len(matching)}"
        )
    allowed = CANONICAL[event]
    for fm in matching:
        if fm not in allowed:
            raise CrossValidationError(
                f"{path}: '{event}' field-map {fm} not in allowed {allowed}"
            )


# ---------------------------------------------------------------------------
# Arm (i): golden byte strings (verb run end-to-end)
# ---------------------------------------------------------------------------

# (case_id, --event value, extra argv, golden line without trailing newline)
GOLDEN_CASES: list[tuple[str, str, list[str], str]] = [
    (
        "plan_approved",
        "plan_approved",
        ["--set", "dispatch_choice=trunk"],
        '{"ts": "%s", "event": "plan_approved", "feature": "f", '
        '"dispatch_choice": "trunk"}' % FIXED_TS,
    ),
    (
        "feature_paused",
        "feature_paused",
        [],
        '{"ts": "%s", "event": "feature_paused", "feature": "f"}' % FIXED_TS,
    ),
    (
        "phase_transition",
        "phase_transition",
        ["--set", "from=plan", "--set", "to=implement"],
        '{"ts": "%s", "event": "phase_transition", "feature": "f", '
        '"from": "plan", "to": "implement"}' % FIXED_TS,
    ),
    (
        "phase_transition_with_tier",
        "phase_transition",
        ["--set", "tier=complex", "--set", "from=implement", "--set", "to=review"],
        '{"ts": "%s", "event": "phase_transition", "feature": "f", '
        '"tier": "complex", "from": "implement", "to": "review"}' % FIXED_TS,
    ),
    (
        "review_verdict",
        "review_verdict",
        ["--set", "verdict=APPROVED", "--set-json", "cycle=1",
         "--set", "requirements_drift=none"],
        '{"ts": "%s", "event": "review_verdict", "feature": "f", '
        '"verdict": "APPROVED", "cycle": 1, "requirements_drift": "none"}'
        % FIXED_TS,
    ),
    (
        "drift_protocol_breach",
        "drift_protocol_breach",
        ["--set", "state=detected", "--set", "suggestion=missing",
         "--set-json", "retries=2"],
        '{"ts": "%s", "event": "drift_protocol_breach", "feature": "f", '
        '"state": "detected", "suggestion": "missing", "retries": 2}' % FIXED_TS,
    ),
    (
        "batch_dispatch",
        "batch_dispatch",
        ["--set-json", "batch=3", "--set-json", "tasks=[1, 2]"],
        '{"ts": "%s", "event": "batch_dispatch", "feature": "f", '
        '"batch": 3, "tasks": [1, 2]}' % FIXED_TS,
    ),
    (
        "criticality_override",
        "criticality_override",
        ["--set", "from=low", "--set", "to=high"],
        '{"ts": "%s", "event": "criticality_override", "feature": "f", '
        '"from": "low", "to": "high"}' % FIXED_TS,
    ),
    (
        "lifecycle_critical_review_skipped",
        "lifecycle_critical_review_skipped",
        ["--set", "phase=plan", "--set", "tier=complex", "--set", "criticality=low"],
        '{"ts": "%s", "event": "lifecycle_critical_review_skipped", '
        '"feature": "f", "phase": "plan", "tier": "complex", '
        '"criticality": "low"}' % FIXED_TS,
    ),
    (
        "lifecycle_start",
        "lifecycle_start",
        ["--set", "tier=simple", "--set", "criticality=medium"],
        '{"ts": "%s", "event": "lifecycle_start", "feature": "f", '
        '"tier": "simple", "criticality": "medium"}' % FIXED_TS,
    ),
    (
        "spec_approved",
        "spec_approved",
        [],
        '{"ts": "%s", "event": "spec_approved", "feature": "f"}' % FIXED_TS,
    ),
    (
        "feature_complete",
        "feature_complete",
        [],
        '{"ts": "%s", "event": "feature_complete", "feature": "f"}' % FIXED_TS,
    ),
]


@pytest.mark.parametrize(
    "case_id,event,extra_argv,golden",
    GOLDEN_CASES,
    ids=[c[0] for c in GOLDEN_CASES],
)
def test_golden_emission(
    case_id: str,
    event: str,
    extra_argv: list[str],
    golden: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verb emits the exact inline golden bytes for the canonical argv."""
    root = _setup_cortex_root(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.setattr(lifecycle_event, "_now_iso", lambda: FIXED_TS)

    rc = _run(["log", "--event", event, "--feature", "f"] + extra_argv)
    assert rc == 0

    line = (
        root / "cortex" / "lifecycle" / "f" / "events.log"
    ).read_text(encoding="utf-8").splitlines()[0]
    assert line == golden, f"{case_id}: golden mismatch\n  got: {line}\n  exp: {golden}"

    # The golden parses back to typed JSON (number/array types survive).
    parsed = json.loads(line)
    assert parsed["event"] == event


def test_batch_dispatch_golden_types_are_numeric_and_array() -> None:
    """Pin batch_dispatch's JSON types directly from a parsed golden."""
    golden = next(c[3] for c in GOLDEN_CASES if c[0] == "batch_dispatch")
    row = json.loads(golden)
    assert row["batch"] == 3 and isinstance(row["batch"], int)
    assert row["tasks"] == [1, 2] and isinstance(row["tasks"], list)


def test_feature_complete_golden_contains_scan_lifecycle_needle() -> None:
    """feature_complete's golden line contains scan_lifecycle.py's needle_tight."""
    golden = next(c[3] for c in GOLDEN_CASES if c[0] == "feature_complete")
    # The exact substring cortex_command/hooks/scan_lifecycle.py searches for.
    assert '"event": "feature_complete"' in golden


# ---------------------------------------------------------------------------
# Arm (ii): on-disk cross-validation over every migrated invocation
# ---------------------------------------------------------------------------

_ONDISK_PARAMS = [
    (file, event, count)
    for file, events in FILE_EVENTS.items()
    for event, count in events.items()
]


@pytest.mark.parametrize(
    "rel_path,event,expected_count",
    _ONDISK_PARAMS,
    ids=[f"{Path(f).name}:{e}" for (f, e, _c) in _ONDISK_PARAMS],
)
def test_ondisk_invocation_matches_canonical(
    rel_path: str, event: str, expected_count: int
) -> None:
    """Each on-disk invocation's field-key set + flag-kinds match the canonical.

    Found-match is exact (== expected_count), so a missing, duplicated, or
    extra invocation fails loud rather than passing an empty/short loop.
    """
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"migrated file missing: {path}"
    # Does not raise on the correct on-disk forms.
    cross_validate(path, event, expected_count)


def test_every_canonical_event_has_a_golden_case() -> None:
    """Sanity: every event in CANONICAL has at least one golden case."""
    golden_events = {c[1] for c in GOLDEN_CASES}
    assert set(CANONICAL) <= golden_events, (
        f"events missing a golden case: {set(CANONICAL) - golden_events}"
    )


def test_found_match_is_anti_vacuous_on_wrong_count() -> None:
    """A deliberately-wrong expected count makes cross_validate fail loud."""
    plan = REPO_ROOT / "skills/lifecycle/references/plan.md"
    with pytest.raises(CrossValidationError):
        cross_validate(plan, "plan_approved", 99)


# ---------------------------------------------------------------------------
# Negative controls — exercised through the FILE-READING path (not synthetic
# strings): the cross-validator must REJECT a mistyped flag-kind and a dropped
# field-key, and must ACCEPT the corrected fixtures (witness the defect, not the
# fixture, triggers rejection).
# ---------------------------------------------------------------------------


def _write_md(path: Path, invocation: str) -> Path:
    path.write_text(
        "Some prose.\n\n```bash\n" + invocation + "\n```\n", encoding="utf-8"
    )
    return path


def test_negative_control_mistyped_flag_kind_rejected(tmp_path: Path) -> None:
    """batch=--set (should be --set-json) is rejected through the file path."""
    bad = _write_md(
        tmp_path / "bad_batch.md",
        "cortex-lifecycle-event log --event batch_dispatch --feature f "
        "--set batch=3 --set-json tasks=[1, 2]",
    )
    with pytest.raises(CrossValidationError):
        cross_validate(bad, "batch_dispatch", 1)

    # Witness: the corrected form (both --set-json) ACCEPTS — proving it is the
    # flag-kind defect, not the fixture file itself, that triggers rejection.
    good = _write_md(
        tmp_path / "good_batch.md",
        "cortex-lifecycle-event log --event batch_dispatch --feature f "
        "--set-json batch=3 --set-json tasks=[1, 2]",
    )
    cross_validate(good, "batch_dispatch", 1)  # must not raise


def test_negative_control_dropped_field_key_rejected(tmp_path: Path) -> None:
    """lifecycle_start missing --set criticality= is rejected via the file path."""
    bad = _write_md(
        tmp_path / "bad_lifecycle_start.md",
        "cortex-lifecycle-event log --event lifecycle_start --feature f "
        "--set tier=simple",
    )
    with pytest.raises(CrossValidationError):
        cross_validate(bad, "lifecycle_start", 1)

    # Witness: restoring --set criticality= ACCEPTS.
    good = _write_md(
        tmp_path / "good_lifecycle_start.md",
        "cortex-lifecycle-event log --event lifecycle_start --feature f "
        "--set tier=simple --set criticality=medium",
    )
    cross_validate(good, "lifecycle_start", 1)  # must not raise
