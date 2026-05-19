"""Golden-file replay tests for the cortex-scan-lifecycle SessionStart hook.

Task 1 deliverable: this module is the *skeleton* established alongside the
captured golden fixtures under ``tests/fixtures/hooks/scan_lifecycle/``.
Each ``test_golden_<case>_additionalContext`` stub asserts the byte-for-byte
``hookSpecificOutput.additionalContext`` substring against the corresponding
``<case>.expected.additionalContext.txt`` fixture.

Task 14 lights up: the stubs now replay the same fixtures through the new
``cortex hooks scan-lifecycle`` Python subcommand (via direct call into
``cortex_command.hooks.scan_lifecycle.main()``), AND the module gains
four table-driven session-mutation tests (P1, P2, SC, OR) exercising the
filesystem-mutation branches enumerated by spec req #6.

Fixture cases per spec req #2:
  (a) no lifecycle dir
  (b) single incomplete feature
  (c) multiple incomplete features
  (d) post-/clear session migration
  (e) Morning Review active
  (f) pipeline-state with executing/paused/failed features

The literal token ``__NO_OUTPUT__`` (on its own line) in an
``.expected.additionalContext.txt`` represents "hook emitted no JSON
envelope" — i.e. an empty stdout from the wrapper / subcommand. Any other
content is asserted as a byte-equivalent additionalContext match.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from cortex_command.hooks import scan_lifecycle as scan_lifecycle_mod
from tests._hook_fixture_helpers import (
    FeatureSpec,
    StageSpec,
    extract_additional_context,
    fixture_expected_path,
    fixture_input_path,
    stage_lifecycle,
)


CASES = (
    "a_no_lifecycle_dir",
    "b_single_incomplete_feature",
    "c_multiple_incomplete_features",
    "d_post_clear_session_migration",
    "e_morning_review_active",
    "f_pipeline_state_with_statuses",
)


NO_OUTPUT_SENTINEL = "__NO_OUTPUT__\n"


def _load_fixture_pair(case: str) -> tuple[dict, str]:
    """Return ``(input_payload, expected_additional_context_or_sentinel)``.

    The input payload's ``cwd`` field still holds the ``__TMPDIR__``
    placeholder — replay code must substitute it for a real staged repo
    path before feeding stdin to the hook / subcommand.
    """
    in_path = fixture_input_path(case)
    expected_path = fixture_expected_path(case)
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    expected = expected_path.read_text(encoding="utf-8")
    return payload, expected


# ----------------------------------------------------------------------------
# Replay machinery
# ----------------------------------------------------------------------------


def _stage_for_case(case: str, tmp_path: Path) -> Path:
    """Stage the lifecycle filesystem state that re-produces fixture ``case``.

    Returns the staged repo root. The returned path is substituted into
    the fixture's ``cwd`` placeholder before driving the hook.

    The state shapes are derived from the golden ``additionalContext``
    text — each case stages exactly enough lifecycle state for the
    Python subcommand to reproduce that text byte-for-byte.
    """
    if case == "a_no_lifecycle_dir":
        # No lifecycle dir at all — early-exit silent path.
        return stage_lifecycle(
            tmp_path,
            StageSpec(create_lifecycle_dir=False),
        )

    if case == "b_single_incomplete_feature":
        # Single feature in "specify" phase (research.md present, no spec.md).
        return stage_lifecycle(
            tmp_path,
            StageSpec(
                features=[
                    FeatureSpec(
                        name="feature-b",
                        research_md="# research\n",
                    )
                ]
            ),
        )

    if case == "c_multiple_incomplete_features":
        # Three features: two in specify, one in plan.
        # Plan phase = spec.md + spec_approved event.
        spec_approved_log = (
            '{"event": "spec_approved"}\n'
        )
        return stage_lifecycle(
            tmp_path,
            StageSpec(
                features=[
                    FeatureSpec(
                        name="feature-c1",
                        research_md="# research c1\n",
                    ),
                    FeatureSpec(
                        name="feature-c2",
                        research_md="# research c2\n",
                    ),
                    FeatureSpec(
                        name="feature-c3",
                        research_md="# research c3\n",
                        spec_md="# spec c3\n",
                        events_log=spec_approved_log,
                    ),
                ]
            ),
        )

    if case == "d_post_clear_session_migration":
        # Single feature in plan phase, .session contains stale id.
        # Phase 1 migration runs because LIFECYCLE_SESSION_ID (stale) !=
        # new session_id (fresh). After migration, .session matches new
        # id and feature-d becomes active.
        spec_approved_log = (
            '{"event": "spec_approved"}\n'
        )
        return stage_lifecycle(
            tmp_path,
            StageSpec(
                features=[
                    FeatureSpec(
                        name="feature-d",
                        research_md="# research d\n",
                        spec_md="# spec d\n",
                        events_log=spec_approved_log,
                        session="OLD-SESSION-ID-d",
                    )
                ]
            ),
        )

    if case == "e_morning_review_active":
        # Pipeline state is "complete" with two merged features that
        # have NO feature_complete event — Morning Review activates.
        # Merged features are suppressed from incomplete-features
        # enumeration, so only the pipeline-context line is emitted.
        return stage_lifecycle(
            tmp_path,
            StageSpec(
                features=[
                    FeatureSpec(
                        name="merged-feature-e1",
                        research_md="# research e1\n",
                    ),
                    FeatureSpec(
                        name="merged-feature-e2",
                        research_md="# research e2\n",
                    ),
                ],
                pipeline_state={
                    "phase": "complete",
                    "features": {
                        "merged-feature-e1": {"status": "merged"},
                        "merged-feature-e2": {"status": "merged"},
                    },
                },
            ),
        )

    if case == "f_pipeline_state_with_statuses":
        # Active pipeline (phase=executing) with three features: one
        # executing, one paused, one failed. Three incomplete lifecycles
        # — no session match → multi-incomplete prompt fires AND
        # pipeline context line is prepended.
        spec_approved_log = (
            '{"event": "spec_approved"}\n'
        )
        return stage_lifecycle(
            tmp_path,
            StageSpec(
                features=[
                    FeatureSpec(
                        name="exec-feature-f1",
                        research_md="# research f1\n",
                        spec_md="# spec f1\n",
                        events_log=spec_approved_log,
                    ),
                    FeatureSpec(
                        name="paused-feature-f2",
                        research_md="# research f2\n",
                    ),
                    FeatureSpec(
                        name="failed-feature-f3",
                        research_md="# research f3\n",
                    ),
                ],
                pipeline_state={
                    "phase": "executing",
                    "features": {
                        "exec-feature-f1": {"status": "executing"},
                        "paused-feature-f2": {"status": "paused"},
                        "failed-feature-f3": {"status": "failed"},
                    },
                },
            ),
        )

    raise AssertionError(f"unhandled fixture case: {case}")  # pragma: no cover


def _run_main(
    payload: dict[str, Any],
    repo: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    lifecycle_session_id: str | None = None,
) -> str:
    """Drive ``scan_lifecycle.main()`` with ``payload`` and return its stdout.

    The fixture payload's ``cwd`` placeholder is substituted with the
    staged repo path. stdin is replaced with a StringIO containing the
    serialized payload. ``LIFECYCLE_SESSION_ID`` env var is set / unset
    per ``lifecycle_session_id`` (None = unset).
    """
    payload = dict(payload)
    payload["cwd"] = str(repo)
    # Strip the synthetic env helper if present in the fixture json.
    env_hint = payload.pop("_lifecycle_session_id_env", None)
    if lifecycle_session_id is None:
        lifecycle_session_id = env_hint

    if lifecycle_session_id is not None:
        monkeypatch.setenv("LIFECYCLE_SESSION_ID", lifecycle_session_id)
    else:
        monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

    # CLAUDE_ENV_FILE: route LIFECYCLE_SESSION_ID export to a tmp file
    # under the repo so the hook's stdin-side-effect is captured but
    # does not pollute the developer environment.
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps(payload))
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0, f"scan_lifecycle.main() returned {rc}"

    captured = capsys.readouterr()
    return captured.out


# ----------------------------------------------------------------------------
# Golden-file replay tests
# ----------------------------------------------------------------------------


def test_golden_a_no_lifecycle_dir_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("a_no_lifecycle_dir")
    assert expected == NO_OUTPUT_SENTINEL

    repo = _stage_for_case("a_no_lifecycle_dir", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    assert stdout == "", (
        f"expected empty stdout for case (a); got: {stdout!r}"
    )


def test_golden_b_single_incomplete_feature_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("b_single_incomplete_feature")
    repo = _stage_for_case("b_single_incomplete_feature", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    ctx = extract_additional_context(stdout)
    assert ctx == expected, (
        f"additionalContext mismatch for case (b)\n"
        f"expected: {expected!r}\n"
        f"got:      {ctx!r}"
    )


def test_golden_c_multiple_incomplete_features_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("c_multiple_incomplete_features")
    repo = _stage_for_case("c_multiple_incomplete_features", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    ctx = extract_additional_context(stdout)
    assert ctx == expected, (
        f"additionalContext mismatch for case (c)\n"
        f"expected: {expected!r}\n"
        f"got:      {ctx!r}"
    )


def test_golden_d_post_clear_session_migration_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("d_post_clear_session_migration")
    repo = _stage_for_case("d_post_clear_session_migration", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    ctx = extract_additional_context(stdout)
    assert ctx == expected, (
        f"additionalContext mismatch for case (d)\n"
        f"expected: {expected!r}\n"
        f"got:      {ctx!r}"
    )


def test_golden_e_morning_review_active_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("e_morning_review_active")
    repo = _stage_for_case("e_morning_review_active", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    ctx = extract_additional_context(stdout)
    assert ctx == expected, (
        f"additionalContext mismatch for case (e)\n"
        f"expected: {expected!r}\n"
        f"got:      {ctx!r}"
    )


def test_golden_f_pipeline_state_with_statuses_additionalContext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, expected = _load_fixture_pair("f_pipeline_state_with_statuses")
    repo = _stage_for_case("f_pipeline_state_with_statuses", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    ctx = extract_additional_context(stdout)
    assert ctx == expected, (
        f"additionalContext mismatch for case (f)\n"
        f"expected: {expected!r}\n"
        f"got:      {ctx!r}"
    )


# ----------------------------------------------------------------------------
# Session-mutation table-driven tests (P1 / P2 / SC / OR)
# ----------------------------------------------------------------------------


def test_session_mutation_P1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**(P1) Phase 1 migration**.

    Stage one incomplete feature with ``.session`` containing the stale
    LIFECYCLE_SESSION_ID. Invoke main() with a new SESSION_ID. After the
    call ``.session`` must contain the new id and ``.session-owner``
    must contain the stale id (spec req #6 P1 branch).
    """
    stale_id = "STALE-SESSION-P1"
    new_id = "NEW-SESSION-P1"

    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-p1",
                    research_md="# research p1\n",
                    spec_md="# spec p1\n",
                    events_log='{"event": "spec_approved"}\n',
                    session=stale_id,
                )
            ]
        ),
    )

    payload = {
        "hook_event_name": "SessionStart",
        "session_id": new_id,
        "cwd": str(repo),
    }
    _run_main(
        payload,
        repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        lifecycle_session_id=stale_id,
    )

    feature_dir = repo / "cortex" / "lifecycle" / "feature-p1"
    session_path = feature_dir / ".session"
    owner_path = feature_dir / ".session-owner"

    assert session_path.is_file(), ".session must exist after P1"
    assert owner_path.is_file(), ".session-owner must exist after P1"

    assert "".join(
        session_path.read_text(encoding="utf-8").split()
    ) == new_id
    assert "".join(
        owner_path.read_text(encoding="utf-8").split()
    ) == stale_id


def test_session_mutation_P2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**(P2) Phase 2 chain migration**.

    Stage two incomplete features whose ``.session-owner`` matches the
    stale id, with no ``.session`` files. Invoke main() with a new
    SESSION_ID. After the call ``.session`` must be written into each
    incomplete feature with the new id, while ``.session-owner`` is
    left unchanged (spec req #6 P2 branch).
    """
    stale_id = "STALE-SESSION-P2"
    new_id = "NEW-SESSION-P2"

    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-p2-a",
                    research_md="# research a\n",
                    session_owner=stale_id,
                ),
                FeatureSpec(
                    name="feature-p2-b",
                    research_md="# research b\n",
                    spec_md="# spec b\n",
                    events_log='{"event": "spec_approved"}\n',
                    session_owner=stale_id,
                ),
            ]
        ),
    )

    payload = {
        "hook_event_name": "SessionStart",
        "session_id": new_id,
        "cwd": str(repo),
    }
    _run_main(
        payload,
        repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        lifecycle_session_id=stale_id,
    )

    lifecycle_dir = repo / "cortex" / "lifecycle"
    for feature_name in ("feature-p2-a", "feature-p2-b"):
        feature_dir = lifecycle_dir / feature_name
        session_path = feature_dir / ".session"
        owner_path = feature_dir / ".session-owner"
        assert session_path.is_file(), (
            f".session must be written into {feature_name} after P2"
        )
        assert "".join(
            session_path.read_text(encoding="utf-8").split()
        ) == new_id, (
            f"{feature_name}/.session must contain new id after P2"
        )
        # .session-owner is left unchanged — still the stale id so
        # chained /clear events can keep migrating.
        assert "".join(
            owner_path.read_text(encoding="utf-8").split()
        ) == stale_id, (
            f"{feature_name}/.session-owner must be unchanged after P2"
        )


def test_session_mutation_SC(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**(SC) Single-feature crash-recovery claim**.

    Stage exactly one incomplete feature with neither ``.session`` nor
    ``.session-owner``. Invoke main() with a SESSION_ID. After the call
    ``.session`` must be written with the new id, ``.session-owner``
    untouched (spec req #6 SC branch).
    """
    new_id = "NEW-SESSION-SC"

    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-sc",
                    research_md="# research sc\n",
                )
            ]
        ),
    )

    payload = {
        "hook_event_name": "SessionStart",
        "session_id": new_id,
        "cwd": str(repo),
    }
    _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )

    feature_dir = repo / "cortex" / "lifecycle" / "feature-sc"
    session_path = feature_dir / ".session"
    owner_path = feature_dir / ".session-owner"

    assert session_path.is_file(), ".session must be written after SC"
    assert "".join(
        session_path.read_text(encoding="utf-8").split()
    ) == new_id
    assert not owner_path.exists(), (
        ".session-owner must NOT be created by the SC branch"
    )


def test_session_mutation_OR(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**(OR) Orphan-``.session-owner`` resurrection — DEPARTURE from bash**.

    Stage one feature whose detected phase is ``complete`` with
    ``.session-owner`` set to the stale id but no ``.session``. Invoke
    main() with a new SESSION_ID. No new ``.session`` must be created
    — the bash hook's resurrection is treated as a latent bug and not
    reproduced (spec req #6 OR branch).
    """
    stale_id = "STALE-SESSION-OR"
    new_id = "NEW-SESSION-OR"

    # Feature is marked complete via a feature_complete event in
    # events.log — detect_lifecycle_phase will short-circuit to
    # phase=complete (step 1).
    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-or",
                    research_md="# research or\n",
                    spec_md="# spec or\n",
                    plan_md="# plan or\n",
                    events_log=(
                        '{"event": "spec_approved"}\n'
                        '{"event": "plan_approved"}\n'
                        '{"event": "feature_complete"}\n'
                    ),
                    session_owner=stale_id,
                )
            ]
        ),
    )

    payload = {
        "hook_event_name": "SessionStart",
        "session_id": new_id,
        "cwd": str(repo),
    }
    _run_main(
        payload,
        repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        lifecycle_session_id=stale_id,
    )

    feature_dir = repo / "cortex" / "lifecycle" / "feature-or"
    session_path = feature_dir / ".session"
    owner_path = feature_dir / ".session-owner"

    assert not session_path.exists(), (
        ".session must NOT be created for an orphan .session-owner "
        "whose feature is complete (OR branch — bash-divergent)"
    )
    # .session-owner remains untouched (we do not delete it).
    assert owner_path.is_file()
    assert "".join(
        owner_path.read_text(encoding="utf-8").split()
    ) == stale_id


# ----------------------------------------------------------------------------
# Meta-test: every CASE has both a fixture pair on disk
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_fixture_pair_present(case: str) -> None:
    in_path = fixture_input_path(case)
    expected_path = fixture_expected_path(case)
    assert in_path.is_file(), f"missing input fixture: {in_path}"
    assert expected_path.is_file(), f"missing expected fixture: {expected_path}"
    # Non-empty invariant (per Task 1 verification).
    assert expected_path.stat().st_size > 0, (
        f"expected fixture is empty: {expected_path}"
    )


def test_all_six_cases_enumerated() -> None:
    """Guard: the CASES tuple covers all six spec-req-#2 cases (a-f)."""
    assert len(CASES) == 6
    prefixes = sorted({c.split("_", 1)[0] for c in CASES})
    assert prefixes == ["a", "b", "c", "d", "e", "f"]
