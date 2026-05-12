"""Positive-control acceptance test for sandbox-denial classifier + renderer.

Spec: ``cortex/lifecycle/add-sandbox-violation-tracker-hook-for-posttoolusebash/spec.md``
R6 (positive-control acceptance test). Constructs a hand-authored fixture
session under ``tmp_path`` and exercises ``collect_sandbox_denials`` and
``render_sandbox_denials`` end-to-end against it.

Fixture scope: this validates the *classifier reading* against a hand-authored
input shape that matches T1's tracker output and T4/T5's sidecar JSON schema.
It does NOT verify writer-reader integration (the manual smoke recipe in T9
covers that). T8 alone passing does not certify production correctness.

Three fixture entries cover the three classifier layers required by R6:

    Entry A: ``cd /fixture && echo x > .git/refs/heads/main``
        — exercises Layer 1 (shell redirection target extraction).
    Entry B: ``cd /fixture && git commit -am 'msg'``
        — exercises Layer 2 (plumbing-tool subcommand mapping for git commit).
    Entry C: ``git some-unmapped-subcommand-variant``
        — exercises Layer 3 (plumbing fallthrough → ``plumbing_eperm``).

Two sidecar files exercise the multi-spawn union behavior:

    orchestrator-1.json: ``/fixture/.git/refs/heads/main``,
        ``/fixture/.git/HEAD``, ``/fixture/.git/packed-refs``
    feature-foo-1.json: ``/other-repo/.git/refs/heads/main``

The minimal ``overnight-state.json`` populates ``project_root: "/fixture"``
(home-repo heuristic) and a ``features`` list with one entry whose
``repo_path: "/other-repo"`` (cross-repo heuristic). This mirrors T6's
inference path that derives home/cross from existing OvernightState fields
without requiring schema extension.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.report import (
    ReportData,
    collect_sandbox_denials,
    render_sandbox_denials,
)


FIXTURE_ID = "overnight-2026-05-05-fixture"


def _write_bash_log(tool_failures_dir: Path) -> None:
    """Write a multi-document YAML bash.log mirroring T1's tracker output.

    Tracker emits per-failure docs separated by ``---`` with these fields:
    ``failure_num``, ``tool``, ``exit_code``, ``timestamp``, ``command`` (YAML
    literal block), ``stderr`` (YAML literal block).  Indentation under the
    ``|`` block scalars must be two spaces (matches the ``sed 's/^/  /'``
    idiom used by the tracker).
    """
    tool_failures_dir.mkdir(parents=True, exist_ok=True)
    bash_log = tool_failures_dir / "bash.log"

    bash_log.write_text(
        # --- Entry A: Layer 1 redirection ---
        "---\n"
        "failure_num: 1\n"
        "tool: Bash\n"
        "exit_code: 1\n"
        "timestamp: 2026-05-05T00:00:01Z\n"
        "command: |\n"
        "  cd /fixture && echo x > .git/refs/heads/main\n"
        "stderr: |\n"
        "  bash: .git/refs/heads/main: Operation not permitted\n"
        # --- Entry B: Layer 2 git commit mapping ---
        "---\n"
        "failure_num: 2\n"
        "tool: Bash\n"
        "exit_code: 1\n"
        "timestamp: 2026-05-05T00:00:02Z\n"
        "command: |\n"
        "  cd /fixture && git commit -am 'msg'\n"
        "stderr: |\n"
        "  error: cannot lock ref 'refs/heads/main': "
        "Operation not permitted\n"
        # --- Entry C: Layer 3 plumbing fallthrough ---
        "---\n"
        "failure_num: 3\n"
        "tool: Bash\n"
        "exit_code: 1\n"
        "timestamp: 2026-05-05T00:00:03Z\n"
        "command: |\n"
        "  git some-unmapped-subcommand-variant\n"
        "stderr: |\n"
        "  error: Operation not permitted\n",
        encoding="utf-8",
    )


def _write_sidecars(sandbox_dir: Path) -> None:
    """Write two sidecar deny-list JSON files matching T4/T5's schema-v2."""
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # Orchestrator sidecar — covers /fixture (home-repo) deny paths.
    (sandbox_dir / "orchestrator-1.json").write_text(
        json.dumps({
            "schema_version": 2,
            "written_at": "2026-05-05T00:00:00Z",
            "spawn_kind": "orchestrator",
            "spawn_id": "orchestrator-1",
            "deny_paths": [
                "/fixture/.git/refs/heads/main",
                "/fixture/.git/HEAD",
                "/fixture/.git/packed-refs",
            ],
        }),
        encoding="utf-8",
    )

    # Feature-dispatch sidecar — covers /other-repo (cross-repo) deny paths.
    # Verifies the union behavior: a separate file contributes its entries to
    # the deny-list set the classifier consults at match time.
    (sandbox_dir / "feature-foo-1.json").write_text(
        json.dumps({
            "schema_version": 2,
            "written_at": "2026-05-05T00:00:00Z",
            "spawn_kind": "feature_dispatch",
            "spawn_id": "feature-foo-1",
            "deny_paths": [
                "/other-repo/.git/refs/heads/main",
            ],
        }),
        encoding="utf-8",
    )


def _write_overnight_state(lifecycle_dir: Path) -> None:
    """Write a minimal overnight-state.json mirroring OvernightState.to_dict.

    Populates ``project_root: "/fixture"`` (matching T6's home-repo heuristic)
    and a ``features`` mapping with one entry whose ``repo_path: "/other-repo"``
    (matching T6's cross-repo heuristic).  The shape mirrors what
    ``cortex_command.overnight.state.load_state`` expects to round-trip.
    """
    lifecycle_dir.mkdir(parents=True, exist_ok=True)
    state_path = lifecycle_dir / "overnight-state.json"

    state_path.write_text(
        json.dumps({
            "session_id": FIXTURE_ID,
            "plan_ref": "test-plan",
            "current_round": 1,
            "phase": "executing",
            "features": {
                "foo": {
                    "status": "pending",
                    "repo_path": "/other-repo",
                },
            },
            "round_history": [],
            "started_at": "2026-05-05T00:00:00Z",
            "updated_at": "2026-05-05T00:00:00Z",
            "project_root": "/fixture",
        }),
        encoding="utf-8",
    )


@pytest.fixture
def fixture_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Construct the hand-authored fixture session under ``tmp_path``.

    Layout:

        <tmp_path>/
          backlog/                                  (sentinel for project root)
          lifecycle/
            overnight-state.json                    (project_root + features)
            sessions/<FIXTURE_ID>/
              tool-failures/bash.log                (3 YAML entries)
              sandbox-deny-lists/orchestrator-1.json
              sandbox-deny-lists/feature-foo-1.json

    chdir into ``tmp_path`` so ``collect_sandbox_denials``'s relative
    ``Path("cortex/lifecycle/sessions/...")`` resolves correctly AND
    ``_resolve_user_project_root()`` (which inspects CWD for a ``cortex/``
    sentinel) can discover the project root.
    """
    # CORTEX_REPO_ROOT is pinned to tmp_path below so the walk is bypassed;
    # no cortex/ sentinel directory is needed here.
    (tmp_path / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)

    # load_state() reads overnight-state.json from cortex/lifecycle/ (rebased path).
    cortex_lifecycle_dir = tmp_path / "cortex" / "lifecycle"
    _write_overnight_state(cortex_lifecycle_dir)

    # collect_sandbox_denials uses a CWD-relative Path("cortex/lifecycle/sessions/..."),
    # so session data stays under cortex/lifecycle/sessions/ relative to CWD (tmp_path).
    legacy_session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / FIXTURE_ID
    _write_bash_log(legacy_session_dir / "tool-failures")
    _write_sidecars(legacy_session_dir / "sandbox-deny-lists")

    monkeypatch.chdir(tmp_path)
    # Ensure CORTEX_REPO_ROOT does not override CWD discovery; if the parent
    # process has it set, scope it to tmp_path for this test.
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    return tmp_path


def test_layer1_redirection_entry_a_classifies_as_home_repo_refs(
    fixture_session: Path,
) -> None:
    """Entry A (``echo x > .git/refs/heads/main``) → ``home_repo_refs``.

    Asserts Layer 1 (shell redirection target extraction) resolves the
    relative target against the ``cd /fixture`` prefix, matches the
    ``/fixture/.git/refs/heads/main`` deny-list entry, and classifies the
    entry under the home-repo refs bucket (project_root == /fixture).
    """
    counts = collect_sandbox_denials(FIXTURE_ID)
    assert counts.get("home_repo_refs", 0) >= 1, (
        f"expected home_repo_refs >= 1 from entry A's L1 redirection; "
        f"got counts={counts!r}"
    )


def test_layer2_git_commit_entry_b_classifies_to_home_repo_bucket(
    fixture_session: Path,
) -> None:
    """Entry B (``git commit -am 'msg'``) → some home-repo-* bucket.

    Asserts Layer 2 (plumbing-tool subcommand mapping) generates the
    candidate write-target list for ``git commit`` (refs/heads/*, HEAD,
    packed-refs, index), matches at least one against the deny-list, and
    classifies under home_repo_refs / home_repo_head / home_repo_packed_refs.

    Per the spec, the entry contributes to *one* of these buckets — the
    classifier returns on the first deny-list match, so the exact bucket
    depends on iteration order over the candidate list. Allow any of the
    three home-repo buckets and require their sum to be ≥ 2 (one for
    entry A's L1 match plus one for entry B's L2 match).
    """
    counts = collect_sandbox_denials(FIXTURE_ID)
    home_repo_total = (
        counts.get("home_repo_refs", 0)
        + counts.get("home_repo_head", 0)
        + counts.get("home_repo_packed_refs", 0)
    )
    assert home_repo_total >= 2, (
        f"expected sum of home_repo_* >= 2 (entry A L1 + entry B L2); "
        f"got counts={counts!r}"
    )


def test_layer3_unmapped_git_subcommand_entry_c_classifies_as_plumbing_eperm(
    fixture_session: Path,
) -> None:
    """Entry C (``git some-unmapped-subcommand-variant``) → ``plumbing_eperm``.

    Asserts Layer 3 (plumbing fallthrough) fires when the leading word is
    ``git`` (in PLUMBING_TOOLS) but the subcommand is NOT in the known
    mapping. Demonstrates the safer ``plumbing_eperm`` bucket vs. the
    ``unclassified_eperm`` catch-all.
    """
    counts = collect_sandbox_denials(FIXTURE_ID)
    assert counts.get("plumbing_eperm", 0) >= 1, (
        f"expected plumbing_eperm >= 1 from entry C's L3 fallthrough; "
        f"got counts={counts!r}"
    )


def test_render_emits_disclosure_and_v1_scope_markers(
    fixture_session: Path,
) -> None:
    """``render_sandbox_denials`` emits the disclosure paragraph + V1 scope.

    Per spec R4 acceptance: rendered output must contain the verbatim
    disclosure paragraph (anchored on ``Bash-routed sandbox denials``) and
    the ``V1 scope`` reference. Also asserts at least one non-zero category
    bullet line is rendered (the suppression rule for zero-count categories
    must not strip every line when counts are non-empty).
    """
    counts = collect_sandbox_denials(FIXTURE_ID)
    data = ReportData(session_id=FIXTURE_ID, sandbox_denials=counts)
    rendered = render_sandbox_denials(data)

    assert "Bash-routed sandbox denials" in rendered, (
        f"expected disclosure paragraph in rendered output; got:\n{rendered}"
    )
    assert "V1 scope" in rendered, (
        f"expected 'V1 scope' marker in rendered output; got:\n{rendered}"
    )
    # At least one bullet line for a non-zero category.
    bullet_lines = [ln for ln in rendered.splitlines() if ln.startswith("- ")]
    assert len(bullet_lines) >= 1, (
        f"expected ≥1 non-zero category bullet line; got:\n{rendered}"
    )
