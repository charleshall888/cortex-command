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
import multiprocessing
import os
import subprocess
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

    # Existing fixtures stage minimal repos without events.log content
    # (they predate the staleness filter). Disable it for these tests;
    # the filter is exercised explicitly by ``test_staleness_filter_*``.
    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")

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


def test_session_title_named_after_active_feature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#8: an active lifecycle feature auto-renames the session.

    ``hookSpecificOutput.sessionTitle`` carries the active feature slug so
    the session is identifiable in the /resume screen without a manual
    ``/rename``. Case (b)'s single incomplete feature becomes active via the
    crash-recovery claim, so its slug is the expected title.
    """
    payload, _expected = _load_fixture_pair("b_single_incomplete_feature")
    repo = _stage_for_case("b_single_incomplete_feature", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    envelope = json.loads(stdout)
    assert envelope["hookSpecificOutput"].get("sessionTitle") == "feature-b"


def test_session_title_absent_without_active_feature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#8 negative: no active feature → no ``sessionTitle`` key.

    Case (c)'s multiple incomplete features leave no single active feature
    (no ``.session`` match, no single-candidate claim), so the hook offers
    context without renaming the session to a feature it did not resolve.
    """
    payload, _expected = _load_fixture_pair("c_multiple_incomplete_features")
    repo = _stage_for_case("c_multiple_incomplete_features", tmp_path)
    stdout = _run_main(
        payload, repo, monkeypatch=monkeypatch, capsys=capsys
    )
    envelope = json.loads(stdout)
    assert "sessionTitle" not in envelope["hookSpecificOutput"]


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
# Concurrent-write serialization test (spec req #11)
# ----------------------------------------------------------------------------


def _concurrent_worker(
    repo_str: str,
    feature_name: str,
    session_id: str,
    stale_id: str,
    barrier: "multiprocessing.synchronize.Barrier",
) -> None:
    """Worker for ``test_session_mutation_concurrent_writes_serialized``.

    Runs in a child process spawned via ``multiprocessing.Process``. Each
    worker waits on the shared ``Barrier`` so two workers begin their
    ``scan_lifecycle.main()`` calls as close to simultaneously as
    possible, then drives the hook against a feature whose ``.session``
    contains ``stale_id``. With Task 4's ``feature_lock`` in place the
    two workers serialize their P1 migrations; without it they could
    interleave and leave ``.session`` + ``.session-owner`` in a
    partially-written / inconsistent state.

    Module-level for pickle-compatibility with the macOS default
    ``spawn`` start method.
    """

    import io as _io
    import json as _json
    import os as _os
    import sys as _sys

    # Build the SessionStart payload exactly like ``_run_main`` does.
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": session_id,
        "cwd": repo_str,
    }
    # Each worker gets its own .claude-env scratch so concurrent
    # appenders don't tear at the env-export file.
    env_file = Path(repo_str) / f".claude-env-{session_id}"
    env_file.write_text("", encoding="utf-8")
    _os.environ["CLAUDE_ENV_FILE"] = str(env_file)
    _os.environ["LIFECYCLE_SESSION_ID"] = stale_id

    _sys.stdin = _io.StringIO(_json.dumps(payload))

    # Synchronize start as tightly as possible — both workers cross
    # the barrier and immediately call into main().
    barrier.wait(timeout=10.0)

    from cortex_command.hooks import scan_lifecycle as _scan

    _scan.main()


def test_session_mutation_concurrent_writes_serialized(
    tmp_path: Path,
) -> None:
    """**(spec req #11)** Concurrent SessionStart writes are serialized.

    Two child processes (multiprocessing.Process) each invoke
    ``scan_lifecycle.main()`` against the same feature directory with
    distinct new session ids. They synchronize on a ``multiprocessing.
    Barrier`` so both start their write paths as close to simultaneously
    as possible. Looped ``ITERATIONS`` times to surface any race window.

    Per-iteration assertions:
      * ``.session`` and ``.session-owner`` both exist (no partial)
      * ``.session`` contains exactly one of the two candidate new ids
        (a complete P1 migration ran end-to-end for one winner)
      * ``.session-owner`` contains the stale id (P1's ``stale_id`` is
        copied from ``.session`` into ``.session-owner`` — both writes
        landed atomically under the per-feature flock)
    """

    iterations = 8
    stale_id = "STALE"
    id_a = "ID_A"
    id_b = "ID_B"
    feature_name = "feature-concurrent"

    # multiprocessing.Process on macOS defaults to "spawn" — ensure we
    # use it explicitly so the test behaves the same on Linux where
    # "fork" is the default and would not exercise spawn-pickling.
    mp_ctx = multiprocessing.get_context("spawn")

    for iteration in range(iterations):
        # Per-iteration tmp dir avoids bleed across loop runs even if
        # a worker leaks state.
        iter_root = tmp_path / f"iter-{iteration}"
        iter_root.mkdir()

        repo = stage_lifecycle(
            iter_root,
            StageSpec(
                features=[
                    FeatureSpec(
                        name=feature_name,
                        research_md="# research conc\n",
                        spec_md="# spec conc\n",
                        events_log='{"event": "spec_approved"}\n',
                        session=stale_id,
                    )
                ]
            ),
        )

        barrier = mp_ctx.Barrier(2)
        proc_a = mp_ctx.Process(
            target=_concurrent_worker,
            args=(str(repo), feature_name, id_a, stale_id, barrier),
        )
        proc_b = mp_ctx.Process(
            target=_concurrent_worker,
            args=(str(repo), feature_name, id_b, stale_id, barrier),
        )

        proc_a.start()
        proc_b.start()
        try:
            proc_a.join(timeout=30.0)
            proc_b.join(timeout=30.0)
        finally:
            # Defensive cleanup — never leak a hung worker into the
            # next iteration.
            for p in (proc_a, proc_b):
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=5.0)
                    if p.is_alive():
                        p.kill()
                        p.join(timeout=5.0)

        assert proc_a.exitcode == 0, (
            f"iter {iteration}: worker A exited {proc_a.exitcode}"
        )
        assert proc_b.exitcode == 0, (
            f"iter {iteration}: worker B exited {proc_b.exitcode}"
        )

        feature_dir = repo / "cortex" / "lifecycle" / feature_name
        session_path = feature_dir / ".session"
        owner_path = feature_dir / ".session-owner"

        assert session_path.is_file(), (
            f"iter {iteration}: .session must exist after concurrent run"
        )
        assert owner_path.is_file(), (
            f"iter {iteration}: .session-owner must exist after concurrent run"
        )

        session_content = "".join(
            session_path.read_text(encoding="utf-8").split()
        )
        owner_content = "".join(
            owner_path.read_text(encoding="utf-8").split()
        )

        assert session_content in (id_a, id_b), (
            f"iter {iteration}: .session must contain exactly one new id "
            f"(a complete migration); got {session_content!r}"
        )
        # The winner that landed in .session is non-deterministic, but
        # whichever it was, .session-owner must carry the STALE id —
        # that's the P1 invariant. If a partial interleave had occurred
        # we would see .session-owner carry the OTHER worker's new id
        # (i.e. the worker whose Phase 1 read STALE from .session but
        # whose .session-owner write landed AFTER the other worker had
        # overwritten .session — leaving owner pointing at a new id,
        # not the stale id).
        assert owner_content == stale_id, (
            f"iter {iteration}: .session-owner must contain stale id "
            f"(P1 invariant under serialization); got {owner_content!r} "
            f"(session={session_content!r})"
        )


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


# ----------------------------------------------------------------------------
# Wrapper behavior tests (spec req #9 — probe-then-exec)
# ----------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parent.parent
_WRAPPER_PATH = _REPO_ROOT / "hooks" / "cortex-scan-lifecycle.sh"
_CORTEX_STUBS_DIR = Path(__file__).resolve().parent / "fixtures" / "cortex_stubs"


def _run_wrapper(
    *,
    stub_subdir: str,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> subprocess.CompletedProcess[str]:
    """Drive the wrapper bash script with a stub ``cortex`` on PATH.

    Prepends ``tests/fixtures/cortex_stubs/<stub_subdir>`` to PATH so the
    wrapper's ``command -v cortex`` and subsequent invocations resolve to
    the stub. The wrapper reads stdin JSON whose ``cwd`` field controls
    the lifecycle-dir predicate — we point it at the staged repo so the
    ``[[ -d "$cwd/cortex/lifecycle" ]]`` predicate passes and execution
    reaches the probe step.
    """
    stub_dir = _CORTEX_STUBS_DIR / stub_subdir
    assert (stub_dir / "cortex").is_file(), f"missing stub: {stub_dir}/cortex"

    # Preserve bash + jq tool paths but route `cortex` to the stub.
    original_path = os.environ.get("PATH", "")
    new_path = f"{stub_dir}{os.pathsep}{original_path}"
    monkeypatch.setenv("PATH", new_path)

    stdin_payload = json.dumps(
        {
            "hook_event_name": "SessionStart",
            "session_id": "wrapper-test-session",
            "cwd": str(repo),
        }
    )

    return subprocess.run(
        ["bash", str(_WRAPPER_PATH)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": new_path},
        check=False,
    )


def test_wrapper_probe_failure_silent_degrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**(spec req #9a)** Probe failure → wrapper exits 0 silently.

    Stubs ``cortex`` so ``--help`` returns nonzero — modeling an older
    CLI that doesn't ship ``hooks scan-lifecycle``. The wrapper must
    short-circuit on probe failure with exit 0, never invoking the real
    subcommand and never propagating an error to the operator.
    """
    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-probe-fail",
                    research_md="# research probe fail\n",
                )
            ]
        ),
    )

    result = _run_wrapper(
        stub_subdir="probe_failure",
        repo=repo,
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 0, (
        "wrapper must exit 0 silently when probe (--help) fails; "
        f"got rc={result.returncode}\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )


def test_wrapper_probe_pass_run_fail_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**(spec req #9b)** Probe passes, run fails → wrapper exits 1.

    Stubs ``cortex`` so ``--help`` returns 0 (probe sees subcommand as
    present) but any non-``--help`` invocation returns 1 (real internal
    error). The wrapper must propagate the actual subcommand's nonzero
    exit code — fail-loud discipline per spec req #9.
    """
    repo = stage_lifecycle(
        tmp_path,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-run-fail",
                    research_md="# research run fail\n",
                )
            ]
        ),
    )

    result = _run_wrapper(
        stub_subdir="probe_pass_run_fail",
        repo=repo,
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 1, (
        "wrapper must propagate nonzero from the actual subcommand run "
        "when the probe passes; "
        f"got rc={result.returncode}\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )


# ----------------------------------------------------------------------------
# Staleness filter + non-lifecycle-dir exclusions
# ----------------------------------------------------------------------------


def test_staleness_filter_drops_old_lifecycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Lifecycle whose last events.log ts is older than threshold is hidden."""
    import datetime

    repo = tmp_path / "repo"
    (repo / "cortex" / "lifecycle").mkdir(parents=True)

    old_ts = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=60)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    stale_dir = repo / "cortex" / "lifecycle" / "stale-feat"
    stale_dir.mkdir()
    (stale_dir / "events.log").write_text(
        '{"ts":"' + old_ts + '","event":"lifecycle_start","feature":"stale-feat"}\n',
        encoding="utf-8",
    )
    (stale_dir / "research.md").write_text("# stale\n", encoding="utf-8")

    fresh_dir = repo / "cortex" / "lifecycle" / "fresh-feat"
    fresh_dir.mkdir()
    (fresh_dir / "events.log").write_text(
        '{"ts":"' + new_ts + '","event":"lifecycle_start","feature":"fresh-feat"}\n',
        encoding="utf-8",
    )
    (fresh_dir / "research.md").write_text("# fresh\n", encoding="utf-8")

    monkeypatch.delenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", raising=False)
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "fresh-feat" in additional
    assert "stale-feat" not in additional


def test_staleness_disabled_when_threshold_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CORTEX_SCAN_LIFECYCLE_STALE_DAYS=0 disables the staleness filter."""
    import datetime

    repo = tmp_path / "repo"
    (repo / "cortex" / "lifecycle").mkdir(parents=True)
    old_ts = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=365)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    stale_dir = repo / "cortex" / "lifecycle" / "ancient-feat"
    stale_dir.mkdir()
    (stale_dir / "events.log").write_text(
        '{"ts":"' + old_ts + '","event":"lifecycle_start","feature":"ancient-feat"}\n',
        encoding="utf-8",
    )
    (stale_dir / "research.md").write_text("# ancient\n", encoding="utf-8")

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "ancient-feat" in additional


def test_sessions_registry_dir_excluded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """sessions/ is the per-session registry, not a feature dir."""
    repo = tmp_path / "repo"
    sessions_dir = repo / "cortex" / "lifecycle" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "deadbeef-cafe-1234").mkdir()

    real_dir = repo / "cortex" / "lifecycle" / "real-feat"
    real_dir.mkdir()
    (real_dir / "research.md").write_text("# real\n", encoding="utf-8")

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "sessions" not in additional
    assert "real-feat" in additional


# ---------------------------------------------------------------------------
# Paused-phase unit tests (R2/R3 acceptance + T5 _interrupted_hint widening)
# ---------------------------------------------------------------------------


def test_encode_paused() -> None:
    """R3: _encode_phase widens to attach :N/M to implement-paused.

    Both base implement and implement-paused must carry the same :N/M
    payload so downstream consumers can render "Implement (N/M tasks
    done) — paused". Bare phases like review-paused carry no payload.
    """
    encode = scan_lifecycle_mod._encode_phase
    assert encode("implement-paused", 3, 5, 0) == "implement-paused:3/5"
    assert encode("implement", 3, 5, 0) == "implement:3/5"
    assert encode("review-paused", 0, 0, 0) == "review-paused"
    assert encode("review", 0, 0, 0) == "review"
    assert encode("implement-rework-paused", 0, 0, 2) == "implement-rework-paused:2"


def test_label_paused() -> None:
    """R2: _phase_label renders " — paused" suffix for *-paused encodings.

    Strips the -paused marker, computes the base label via the existing
    rules, then appends " — paused". Works for both bare (review-paused)
    and compound (implement-paused:3/5) wire shapes.
    """
    label = scan_lifecycle_mod._phase_label
    assert label("implement-paused:3/5") == "Implement (3/5 tasks done) — paused"
    assert label("review-paused") == "Review — paused"
    assert label("implement:3/5") == "Implement (3/5 tasks done)"
    assert label("review") == "Review"
    assert label("implement-rework-paused:2") == (
        "Implement — rework (review cycle 2) — paused"
    )


def test_interrupted_hint_paused() -> None:
    """T5: _interrupted_hint recognises -paused wire format.

    The resume hint text is identical for active vs paused implement
    features — operator action is the same per spec R10. Without this
    widening, paused implement features would silently lose the
    Interrupted: ... Resume with ... line that the SessionStart hook
    exists to provide.
    """
    hint = scan_lifecycle_mod._interrupted_hint
    h = hint("implement-paused:3/5", "my-feature")
    assert "Resume with" in h
    assert "3 of 5" in h
    assert "/cortex-core:lifecycle my-feature" in h
    # Active implement (no paused suffix) keeps the same hint shape.
    h2 = hint("implement:3/5", "my-feature")
    assert "Resume with" in h2
    assert "3 of 5" in h2
    # implement-rework-paused: the rework hint still fires.
    h3 = hint("implement-rework-paused:2", "my-feature")
    assert "Resume with" in h3
    assert "review cycle 2" in h3
    # review-paused: no hint (review is not an in-progress phase that
    # needs a resume nudge — kept consistent with the existing
    # behaviour for bare review).
    assert hint("review-paused", "my-feature") == ""


# ---------------------------------------------------------------------------
# T11: backlog index.json loader (single read per hook invocation)
# ---------------------------------------------------------------------------


def test_index_json_loaded(tmp_path: Path) -> None:
    """T11: _load_backlog_status_map returns slug→status from index.json."""
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "index.json").write_text(
        json.dumps([
            {"id": 1, "title": "A", "lifecycle_slug": "feat-a", "status": "in_progress"},
            {"id": 2, "title": "B", "lifecycle_slug": "feat-b", "status": "complete"},
        ]),
        encoding="utf-8",
    )
    mapping, duplicates = scan_lifecycle_mod._load_backlog_status_map(tmp_path)
    assert mapping == {"feat-a": "in_progress", "feat-b": "complete"}
    assert duplicates == []


def test_index_json_absent_empty_map(tmp_path: Path) -> None:
    """T11: missing/unparseable index.json fails open with ({}, [])."""
    # Case 1: file absent entirely.
    mapping, duplicates = scan_lifecycle_mod._load_backlog_status_map(tmp_path)
    assert mapping == {}
    assert duplicates == []
    # Case 2: file present but unparseable.
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "index.json").write_text("{not json}", encoding="utf-8")
    mapping2, duplicates2 = scan_lifecycle_mod._load_backlog_status_map(tmp_path)
    assert mapping2 == {}
    assert duplicates2 == []
    # Case 3: file present but wrong shape (dict instead of list).
    (backlog_dir / "index.json").write_text(
        json.dumps({"not": "a list"}), encoding="utf-8"
    )
    mapping3, duplicates3 = scan_lifecycle_mod._load_backlog_status_map(tmp_path)
    assert mapping3 == {}
    assert duplicates3 == []


def test_index_json_duplicate_first_wins(tmp_path: Path) -> None:
    """T11: duplicate lifecycle_slug — first occurrence wins, dup recorded."""
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "index.json").write_text(
        json.dumps([
            {"id": 1, "title": "first", "lifecycle_slug": "feat-x", "status": "in_progress"},
            {"id": 2, "title": "second", "lifecycle_slug": "feat-x", "status": "complete"},
            {"id": 3, "title": "ok", "lifecycle_slug": "feat-y", "status": "in_progress"},
        ]),
        encoding="utf-8",
    )
    mapping, duplicates = scan_lifecycle_mod._load_backlog_status_map(tmp_path)
    assert mapping == {"feat-x": "in_progress", "feat-y": "in_progress"}
    assert duplicates == ["feat-x"]


# ---------------------------------------------------------------------------
# T12: terminal-vs-non-terminal mismatch predicate + render annotation
# ---------------------------------------------------------------------------


_FIXTURES_HOOKS = Path(__file__).resolve().parent / "fixtures" / "hooks" / "scan_lifecycle"


def _stage_t12_fixture(repo: Path, fixture_name: str, slug: str) -> None:
    """Copy a static T12 fixture under repo/cortex/lifecycle/<slug>/."""
    import shutil

    src = _FIXTURES_HOOKS / fixture_name
    dst = repo / "cortex" / "lifecycle" / slug
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        shutil.copy2(entry, dst / entry.name)


def _write_t12_index(repo: Path, entries: list[dict]) -> None:
    backlog = repo / "cortex" / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    (backlog / "index.json").write_text(json.dumps(entries), encoding="utf-8")


def test_terminal_mismatch_075_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T12 case (a): events=implement (1/3) + backlog=complete → mismatch fires.

    Renders the others-enumeration line with [mismatch: backlog=complete].
    The active feature is set to a separate feature so 075-shape appears
    as an "other".
    """
    repo = tmp_path / "repo"
    _stage_t12_fixture(repo, "075-shape", "075-shape")
    _stage_t12_fixture(repo, "clean-alignment", "clean-alignment")
    _write_t12_index(repo, [
        {"id": 75, "title": "075", "lifecycle_slug": "075-shape", "status": "complete"},
        {"id": 90, "title": "clean", "lifecycle_slug": "clean-alignment", "status": "in_progress"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "075-shape" in additional
    assert "[mismatch: backlog=complete]" in additional


def test_terminal_mismatch_209_shape_no_annotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T12 case (b): paused implement + backlog=in_progress → no mismatch.

    Both sides non-terminal, so the predicate returns False and no
    [mismatch: ...] annotation appears. The label still carries the
    " — paused" suffix from T2/T4.
    """
    repo = tmp_path / "repo"
    _stage_t12_fixture(repo, "209-shape-post-fix", "209-shape-post-fix")
    _write_t12_index(repo, [
        {"id": 209, "title": "209", "lifecycle_slug": "209-shape-post-fix", "status": "in_progress"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "209-shape-post-fix" in additional
    assert "— paused" in additional
    assert "[mismatch:" not in additional


def test_active_header_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T12: active-feature header carries [mismatch: backlog=...] annotation.

    When the active feature itself is the mismatched one (only one
    incomplete lifecycle → crash-recovery claim makes it active), the
    annotation must surface on the "Active lifecycle: ... | Phase: ..."
    line, not just the others-enumeration.
    """
    repo = tmp_path / "repo"
    _stage_t12_fixture(repo, "075-shape", "075-shape")
    _write_t12_index(repo, [
        {"id": 75, "title": "075", "lifecycle_slug": "075-shape", "status": "complete"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    assert "Active lifecycle: 075-shape" in additional
    assert "[mismatch: backlog=complete]" in additional


# ---------------------------------------------------------------------------
# T13: mismatch-first sort + soft-budget truncation + header fragment
# ---------------------------------------------------------------------------


def _stage_minimal_feature(repo: Path, slug: str) -> None:
    """Stage a minimal lifecycle dir that detect_lifecycle_phase will see
    as 'plan' phase (spec.md present, no plan.md). Cheap and predictable.
    """
    feat_dir = repo / "cortex" / "lifecycle" / slug
    feat_dir.mkdir(parents=True, exist_ok=True)
    (feat_dir / "events.log").write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "event": "spec_approved", "feature": slug}) + "\n",
        encoding="utf-8",
    )
    (feat_dir / "spec.md").write_text(f"# spec {slug}\n", encoding="utf-8")


def test_mismatch_first_sort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T13: mismatched entries sort before non-mismatch entries, preserving
    original relative order within each group (stable sort).
    """
    repo = tmp_path / "repo"
    # Create 4 features in slug-order so the lifecycle iteration is
    # deterministic (sorted iterdir): a-first, b-second, c-third, d-fourth.
    # Mark b and d as mismatched via the index.json (status=complete on
    # non-terminal events). a and c stay non-mismatched (in_progress).
    for slug in ("a-first", "b-second", "c-third", "d-fourth"):
        _stage_minimal_feature(repo, slug)
    _write_t12_index(repo, [
        {"id": 1, "title": "a", "lifecycle_slug": "a-first", "status": "in_progress"},
        {"id": 2, "title": "b", "lifecycle_slug": "b-second", "status": "complete"},
        {"id": 3, "title": "c", "lifecycle_slug": "c-third", "status": "in_progress"},
        {"id": 4, "title": "d", "lifecycle_slug": "d-fourth", "status": "complete"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)

    # b-second and d-fourth (mismatched) should appear BEFORE
    # a-first and c-third in the enumeration.
    b_idx = additional.find("b-second")
    d_idx = additional.find("d-fourth")
    a_idx = additional.find("a-first")
    c_idx = additional.find("c-third")
    assert -1 not in (b_idx, d_idx, a_idx, c_idx), additional
    assert b_idx < a_idx, f"b-second should sort before a-first in {additional!r}"
    assert d_idx < a_idx, f"d-fourth should sort before a-first in {additional!r}"
    # Within each group, original order is preserved (b before d, a before c).
    assert b_idx < d_idx, f"stable sort: b before d in {additional!r}"
    assert a_idx < c_idx, f"stable sort: a before c in {additional!r}"


def test_soft_budget_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T13: when assembled block exceeds 9000 chars, non-mismatch entries
    are dropped from the end with a '  … +N more' line. Mismatches are
    never dropped.
    """
    repo = tmp_path / "repo"
    # Create 200 non-mismatch features with long slugs to blow past the
    # 9000-char budget, plus 1 mismatch that must survive truncation.
    long_suffix = "x" * 60
    non_mismatch_slugs = [f"slug-non-{i:03d}-{long_suffix}" for i in range(200)]
    mismatch_slug = f"slug-mismatched-zzz-{long_suffix}"

    for slug in non_mismatch_slugs:
        _stage_minimal_feature(repo, slug)
    _stage_minimal_feature(repo, mismatch_slug)

    entries = [
        {"id": i, "title": slug, "lifecycle_slug": slug, "status": "in_progress"}
        for i, slug in enumerate(non_mismatch_slugs)
    ]
    entries.append(
        {"id": 999, "title": mismatch_slug, "lifecycle_slug": mismatch_slug, "status": "complete"}
    )
    _write_t12_index(repo, entries)

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)

    # The mismatched feature must appear (mismatches are never dropped).
    assert mismatch_slug in additional
    # A "  … +N more" line should appear once truncation kicks in.
    assert "  … +" in additional
    assert " more" in additional
    # Final block should be at or under the budget (with small slack for
    # surrounding context/metrics — we mainly verify truncation activated).
    assert len(additional) <= 10000, f"block size {len(additional)} > 10000"


def test_mismatches_header_fragment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T13: when mismatch_count >= 1, header carries ' — mismatches: N total'.

    Header fragment uses the count BEFORE truncation, so even if some
    entries are dropped by the soft-budget logic, the count reflects the
    full mismatch population at scan time.
    """
    repo = tmp_path / "repo"
    _stage_minimal_feature(repo, "feature-x")
    _stage_minimal_feature(repo, "feature-y")
    _stage_minimal_feature(repo, "feature-z")
    _write_t12_index(repo, [
        {"id": 1, "title": "x", "lifecycle_slug": "feature-x", "status": "complete"},
        {"id": 2, "title": "y", "lifecycle_slug": "feature-y", "status": "complete"},
        {"id": 3, "title": "z", "lifecycle_slug": "feature-z", "status": "in_progress"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)
    # Three features, no session match → multi-incomplete prompt OR
    # active-feature branch when single-incomplete claim fires. With three
    # incomplete features, we land in either path; the header fragment
    # only attaches to the active-feature "Other incomplete lifecycles:"
    # branch. To make the test deterministic, we expect the count to
    # appear when the active branch is selected — and otherwise the
    # multi-incomplete prompt does not get the fragment by design.
    # Probe the actual branch chosen by checking which header is present.
    if "Other incomplete lifecycles:" in additional:
        assert "mismatches: 2 total" in additional, additional
    else:
        # Multi-incomplete prompt branch — no fragment expected.
        assert "Multiple incomplete lifecycles" in additional


# ---------------------------------------------------------------------------
# T14: session-bound JSONL diagnostic
# ---------------------------------------------------------------------------


def test_session_diagnostic_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T14: per-candidate JSONL diagnostic appended under the session dir."""
    repo = tmp_path / "repo"
    _stage_minimal_feature(repo, "diag-feat")
    _write_t12_index(repo, [
        {"id": 1, "title": "diag", "lifecycle_slug": "diag-feat", "status": "in_progress"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "test-session-uuid")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0

    diag_path = (
        repo / "cortex" / "lifecycle" / "sessions" / "test-session-uuid"
        / "scan-lifecycle-diag.jsonl"
    )
    assert diag_path.is_file(), f"diagnostic not written at {diag_path}"
    lines = [ln for ln in diag_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1, f"expected ≥1 diagnostic record, got {lines!r}"
    record = json.loads(lines[0])
    # Schema sanity: required fields present per spec R14.
    for key in (
        "ts", "feature", "decision", "exclude_reason", "latest_event_ts",
        "threshold_days", "last_event", "events_phase", "backlog_status",
        "index_json_resolved", "mismatch",
    ):
        assert key in record, f"diagnostic record missing {key!r}: {record!r}"
    assert record["feature"] == "diag-feat"
    assert record["decision"] == "included"
    assert record["exclude_reason"] is None
    assert record["events_phase"] == "plan"
    assert record["backlog_status"] == "in_progress"
    assert record["index_json_resolved"] is True
    assert record["mismatch"] is False


def test_session_diagnostic_silent_when_session_id_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T14: with LIFECYCLE_SESSION_ID unset, no diagnostic file is written."""
    repo = tmp_path / "repo"
    _stage_minimal_feature(repo, "silent-feat")

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    # The sessions directory should not exist OR should not contain a
    # diag file (no session id → silent no-op per spec).
    sessions_dir = repo / "cortex" / "lifecycle" / "sessions"
    if sessions_dir.is_dir():
        for child in sessions_dir.iterdir():
            assert not (child / "scan-lifecycle-diag.jsonl").exists(), (
                f"diagnostic unexpectedly written under {child}"
            )


# ---------------------------------------------------------------------------
# T15: end-to-end SessionStart envelope integration
# ---------------------------------------------------------------------------


def test_e2e_session_start_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T15: full integration — paused label + mismatch annotation + header.

    Stages three lifecycle dirs:
      (a) implement (1/3 done) with backlog=complete  → terminal mismatch
      (b) paused implement (0/3 done) with backlog=in_progress → no mismatch
      (c) implement (1/3 done) with backlog=in_progress → clean alignment

    Then invokes scan_lifecycle.main() with the standard SessionStart
    envelope and asserts the rendered additionalContext satisfies all
    four acceptance criteria simultaneously.
    """
    repo = tmp_path / "repo"
    # (a) terminal-mismatch
    _stage_t12_fixture(repo, "075-shape", "a-mismatch")
    # (b) paused implement
    _stage_t12_fixture(repo, "209-shape-post-fix", "b-paused")
    # (c) clean alignment
    _stage_t12_fixture(repo, "clean-alignment", "c-clean")
    _write_t12_index(repo, [
        {"id": 1, "title": "a", "lifecycle_slug": "a-mismatch", "status": "complete"},
        {"id": 2, "title": "b", "lifecycle_slug": "b-paused", "status": "in_progress"},
        {"id": 3, "title": "c", "lifecycle_slug": "c-clean", "status": "in_progress"},
    ])

    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0
    additional = extract_additional_context(capsys.readouterr().out)

    # (1) paused feature carries " — paused" label.
    assert "b-paused" in additional
    assert "— paused" in additional
    # (2) mismatched feature carries [mismatch: backlog=complete].
    assert "a-mismatch" in additional
    assert "[mismatch: backlog=complete]" in additional
    # (3) header fragment reports 1 total mismatch.
    assert "mismatches: 1 total" in additional
    # (4) clean feature has no mismatch annotation on its line.
    # Pick the c-clean entry line and verify no [mismatch:] on it.
    for line in additional.splitlines():
        if "c-clean" in line:
            assert "[mismatch:" not in line, (
                f"clean-alignment feature should not carry mismatch annotation: {line!r}"
            )


def test_session_diagnostic_excluded_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T14 rework: stale-excluded candidates also emit a diagnostic record
    with decision='excluded' and exclude_reason='stale'.

    Without this emission, post-mortem debug of "why did the SessionStart
    enumeration silently drop this feature?" is impossible — exactly the
    failure mode the R14 spec calls out under Non-Requirements ("future
    #075 staleness-filter bypass debuggable").
    """
    import datetime as _dt

    repo = tmp_path / "repo"
    # Create a stale feature: events.log with an ancient ts so it falls
    # outside the 30-day staleness window (default).
    feat_dir = repo / "cortex" / "lifecycle" / "stale-feat"
    feat_dir.mkdir(parents=True, exist_ok=True)
    old_ts = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=120)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    (feat_dir / "events.log").write_text(
        json.dumps({"ts": old_ts, "event": "lifecycle_start", "feature": "stale-feat"}) + "\n",
        encoding="utf-8",
    )
    (feat_dir / "research.md").write_text("# stale\n", encoding="utf-8")

    # Default staleness threshold (30 days) applies; ensure env is unset.
    monkeypatch.delenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", raising=False)
    env_file = repo / ".claude-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "stale-diag-uuid")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "x", "cwd": str(repo)})),
    )

    rc = scan_lifecycle_mod.main()
    assert rc == 0

    diag_path = (
        repo / "cortex" / "lifecycle" / "sessions" / "stale-diag-uuid"
        / "scan-lifecycle-diag.jsonl"
    )
    assert diag_path.is_file(), f"diagnostic not written at {diag_path}"
    lines = [ln for ln in diag_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Locate the stale-feat record.
    stale_records = [
        json.loads(ln) for ln in lines
        if json.loads(ln).get("feature") == "stale-feat"
    ]
    assert len(stale_records) == 1, (
        f"expected exactly one diagnostic for stale-feat, got {stale_records!r}"
    )
    record = stale_records[0]
    assert record["decision"] == "excluded", record
    assert record["exclude_reason"] == "stale", record
    # events_phase should be None for stale exclusions (phase detection skipped).
    assert record["events_phase"] is None, record
    # latest_event_ts surfaces the old ts so post-mortem can see WHY it's stale.
    assert record["latest_event_ts"] == old_ts, record
    assert record["threshold_days"] == 30, record


# ---------------------------------------------------------------------------
# Metrics-summary float rounding
# ---------------------------------------------------------------------------


def test_metrics_summary_line_rounds_floats_to_two_decimals(
    tmp_path: Path,
) -> None:
    """Float aggregates render rounded to 2 decimals; ints pass through.

    ``avg_task_count=9.885714285714286`` previously leaked its full float
    repr into the SessionStart context line; it must now render as
    ``9.89``. The int path stays byte-identical (golden fixtures b/d pin
    the bare ``avg 0 tasks`` form), so ``2`` renders as ``"2"`` while the
    float ``4.0`` renders as ``"4.0"``.
    """
    metrics_file = tmp_path / "metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "features": {"feat-a": {}, "feat-b": {}},
                "aggregates": {
                    "simple": {
                        "avg_task_count": 9.885714285714286,
                        "avg_rework_cycles": 0.2857142857142857,
                    },
                    "complex": {
                        "avg_task_count": 4.0,
                        "avg_rework_cycles": 2,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    line = scan_lifecycle_mod._metrics_summary_line(metrics_file)

    assert line == (
        "Metrics: 2 completed features | "
        "Simple: avg 9.89 tasks, 0.29 rework | "
        "Complex: avg 4.0 tasks, 2 rework"
    ), f"unexpected summary line: {line!r}"
