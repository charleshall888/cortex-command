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
