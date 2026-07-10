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

(ii) ON-DISK CROSS-VALIDATION — parse EVERY high-level subcommand invocation
    (``cortex-lifecycle-event <event-subcommand> ...``, the Phase 2 form that
    replaced ``log --event X --set…``) out of each migrated ``.md`` (tolerating
    fenced ```` ```bash ```` blocks and placeholder values like ``--from <...>``
    or ``--tasks '[<task IDs>]'`` — the flag NAMES are concrete even when the
    value is a placeholder), and assert each invocation's flag set is a subset
    of the subcommand's declared flags with all required flags present. The
    contract is validated against the verb's own ``_EVENT_SUBCOMMANDS`` table
    (single source of truth), not a hand-maintained field map. A fail-loud
    found-match check asserts the parser located exactly the expected number of
    invocations per (file, event), so a parse that finds zero/too-few/too-many
    fails rather than passing an empty loop.

**Residual limitation (documented, not closed):** arm (ii) detects on-disk
DRIFT FROM the table's declared flags, not a table that is itself wrong in
lockstep with the ``.md``. Arm (i)'s golden is the independent type/spacing
anchor (it still drives the intact ``log`` path the subcommands funnel into).

``phase_transition`` is NON-UNIFORM across sites: most rows carry ``{from,to}``,
but ``implement.md`` §4 legitimately carries ``{tier,from,to}``. ``--tier`` is
an optional (declared, non-required) flag, so both forms validate.
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


# On-disk form (Phase 2): ``cortex-lifecycle-event <subcommand> --feature X
# --flag val ...`` where ``<subcommand>`` != ``log`` and each event's flag set
# is owned by the verb's ``_EVENT_SUBCOMMANDS`` table — the single source of
# truth this arm validates against (no hand-maintained field map to drift).
from cortex_command.lifecycle_event import _EVENT_SUBCOMMANDS

# event_name -> subcommand (1:1 with the table).
_EVENT_TO_SUB: dict[str, str] = {
    event: sub for sub, (event, _specs) in _EVENT_SUBCOMMANDS.items()
}

_SUBCMD_RE = re.compile(r"cortex-lifecycle-event\s+(?!log\b)([a-z][a-z0-9-]*)\b")
_FLAG_RE = re.compile(r"(--[a-z][a-z0-9-]+)")


class CrossValidationError(Exception):
    """Raised when an on-disk invocation drifts from the canonical contract."""


def parse_invocations(path: Path) -> list[tuple[int, str, set[str]]]:
    """Return ``[(lineno, subcommand, {--flag, ...}), ...]``.

    Only the subcommand name and the set of option flags (values, often
    placeholders, ignored) are extracted. ``log``-form lines are skipped — the
    generic escape hatch is not a high-level subcommand and is validated by the
    golden arm, not here.
    """
    out: list[tuple[int, str, set[str]]] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "cortex-lifecycle-event" not in line:
            continue
        m = _SUBCMD_RE.search(line)
        if not m or m.group(1) not in _EVENT_SUBCOMMANDS:
            continue
        flags = set(_FLAG_RE.findall(line))
        out.append((lineno, m.group(1), flags))
    return out


def _declared_and_required(subcommand: str) -> tuple[set[str], set[str]]:
    """Return (declared, required) flag sets for *subcommand* from the table."""
    _event, specs = _EVENT_SUBCOMMANDS[subcommand]
    declared = {"--feature"} | {flag for (flag, *_rest) in specs}
    required = {"--feature"} | {
        flag for (flag, _ek, _kind, req, _choices) in specs if req
    }
    return declared, required


# Per-file expected invocation counts per event (the on-disk reality). Keyed by
# event name; the subcommand is resolved via ``_EVENT_TO_SUB``. The
# ``interactive_worktree_entered`` emission moved out of implement.md into
# worktree-entry.md in the lifecycle-corpus-trim-wave-2 route-conditional
# extraction, so it is cross-validated against that file now.
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
    "skills/lifecycle/references/worktree-entry.md": {
        "interactive_worktree_entered": 1,
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
    "skills/lifecycle/references/refine-delegation.md": {
        "phase_transition": 1,
    },
}


def cross_validate(path: Path, event: str, expected_count: int) -> None:
    """Fail loud if *event*'s on-disk subcommand invocations drift from the table.

    Raises ``CrossValidationError`` when the found count != *expected_count*
    (anti-vacuous), when any invocation uses a flag the subcommand does not
    declare, or when a required flag is missing.
    """
    subcommand = _EVENT_TO_SUB[event]
    matching = [
        flags for (_ln, sub, flags) in parse_invocations(path)
        if sub == subcommand
    ]
    if len(matching) != expected_count:
        raise CrossValidationError(
            f"{path}: expected {expected_count} '{subcommand}' invocation(s), "
            f"found {len(matching)}"
        )
    declared, required = _declared_and_required(subcommand)
    for flags in matching:
        undeclared = flags - declared
        if undeclared:
            raise CrossValidationError(
                f"{path}: '{subcommand}' uses undeclared flags {undeclared}"
            )
        missing = required - flags
        if missing:
            raise CrossValidationError(
                f"{path}: '{subcommand}' missing required flags {missing}"
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
        "lifecycle_cancelled",
        "lifecycle_cancelled",
        [],
        '{"ts": "%s", "event": "lifecycle_cancelled", "feature": "f"}' % FIXED_TS,
    ),
    (
        "feature_complete",
        "feature_complete",
        [],
        '{"ts": "%s", "event": "feature_complete", "feature": "f"}' % FIXED_TS,
    ),
    (
        "interactive_worktree_entered",
        "interactive_worktree_entered",
        ["--set", "worktree_path=/tmp/wt"],
        '{"ts": "%s", "event": "interactive_worktree_entered", "feature": "f", '
        '"worktree_path": "/tmp/wt"}' % FIXED_TS,
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
# Typed-subcommand emission path (epic 371 Phase B): the new typed
# `lifecycle-cancelled` subcommand and the optional `spec-approved --decision`
# consent field are exercised through the subcommand dispatch (not the `log`
# escape hatch), pinning the row the future wrapper verbs will emit.
# ---------------------------------------------------------------------------


def _emit_and_read_line(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Run *argv* through the verb in an isolated root; return the first row."""
    root = _setup_cortex_root(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.setattr(lifecycle_event, "_now_iso", lambda: FIXED_TS)
    rc = _run(argv)
    assert rc == 0
    return (
        root / "cortex" / "lifecycle" / "f" / "events.log"
    ).read_text(encoding="utf-8").splitlines()[0]


def test_typed_lifecycle_cancelled_subcommand_emits_base_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`lifecycle-cancelled --feature f` writes the bare typed event row."""
    line = _emit_and_read_line(
        ["lifecycle-cancelled", "--feature", "f"], tmp_path, monkeypatch
    )
    assert line == (
        '{"ts": "%s", "event": "lifecycle_cancelled", "feature": "f"}' % FIXED_TS
    )
    assert json.loads(line)["event"] == "lifecycle_cancelled"


def test_typed_spec_approved_carries_decision_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`spec-approved --decision approved` emits a row carrying decision=approved."""
    line = _emit_and_read_line(
        ["spec-approved", "--feature", "f", "--decision", "approved"],
        tmp_path,
        monkeypatch,
    )
    row = json.loads(line)
    assert row["event"] == "spec_approved"
    assert row["decision"] == "approved"


def test_typed_spec_approved_omits_decision_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The optional decision field is dropped entirely when the flag is omitted."""
    line = _emit_and_read_line(
        ["spec-approved", "--feature", "f"], tmp_path, monkeypatch
    )
    assert line == (
        '{"ts": "%s", "event": "spec_approved", "feature": "f"}' % FIXED_TS
    )
    assert "decision" not in json.loads(line)


def test_spec_approved_decision_enum_is_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-enum decision value is rejected by argparse (SystemExit)."""
    root = _setup_cortex_root(tmp_path)
    monkeypatch.chdir(root)
    with pytest.raises(SystemExit):
        _run(["spec-approved", "--feature", "f", "--decision", "rejected"])


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


def test_every_subcommand_event_has_a_golden_case() -> None:
    """Sanity: every event owned by a subcommand has at least one golden case."""
    golden_events = {c[1] for c in GOLDEN_CASES}
    table_events = {event for (event, _specs) in _EVENT_SUBCOMMANDS.values()}
    assert table_events <= golden_events, (
        f"events missing a golden case: {table_events - golden_events}"
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


def test_negative_control_undeclared_flag_rejected(tmp_path: Path) -> None:
    """An undeclared flag on a subcommand is rejected through the file path."""
    bad = _write_md(
        tmp_path / "bad_batch.md",
        "cortex-lifecycle-event batch-dispatch --feature f "
        "--batch 3 --tasks [1,2] --bogus x",
    )
    with pytest.raises(CrossValidationError):
        cross_validate(bad, "batch_dispatch", 1)

    # Witness: the declared-only form ACCEPTS — proving it is the undeclared
    # flag, not the fixture file itself, that triggers rejection.
    good = _write_md(
        tmp_path / "good_batch.md",
        "cortex-lifecycle-event batch-dispatch --feature f "
        "--batch 3 --tasks [1,2]",
    )
    cross_validate(good, "batch_dispatch", 1)  # must not raise


def test_negative_control_dropped_required_flag_rejected(tmp_path: Path) -> None:
    """lifecycle-start missing required --criticality is rejected via the file path."""
    bad = _write_md(
        tmp_path / "bad_lifecycle_start.md",
        "cortex-lifecycle-event lifecycle-start --feature f --tier simple",
    )
    with pytest.raises(CrossValidationError):
        cross_validate(bad, "lifecycle_start", 1)

    # Witness: restoring --criticality ACCEPTS.
    good = _write_md(
        tmp_path / "good_lifecycle_start.md",
        "cortex-lifecycle-event lifecycle-start --feature f "
        "--tier simple --criticality medium",
    )
    cross_validate(good, "lifecycle_start", 1)  # must not raise
