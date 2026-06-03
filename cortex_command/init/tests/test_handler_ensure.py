"""Acceptance tests for ``cortex init --ensure`` (Task 6 / spec R4–R8).

Covers the full dispatch matrix and acceptance bundles from the spec:
- R4 cases: (i) marker-present + hash-match (no-op), (ii) marker-present +
  hash-mismatch (refresh), (iii-a) clean scratch repo, (iii-b) empty cortex/
  dir, (iv) marker-absent + foreign cortex/ content (exit 2 + diagnostic).
- Mutex: ``--ensure --update`` rejected by argparse.
- R6 cases: lock-check timeout (exit 2 within 6s), lock-check clear
  immediately, mid-poll clear via background thread.
- R7 case: ``CORTEX_AUTO_ENSURE=0`` silent no-op.
- R8 cases: truncated marker with cortex_version (warning + refresh), marker
  without cortex_version (exit 2 foreign-artifact), malformed cortex_version
  (exit 2 foreign-artifact), non-JSON content (exit 2 unparseable JSON), R8
  recovery with extra cortex/ content (warning + refresh — covers the
  one-time post-Phase-3 migration storm where existing cortex repos have
  backlog/lifecycle/requirements subdirs alongside the pre-Phase-1 marker),
  unwritable cortex/ (exit non-zero with path-named diagnostic).

Most tests call ``handler._run_ensure`` directly (or ``handler.main`` with a
stubbed ``args.path``) to avoid the subprocess + sandbox blocker on
``~/.claude/settings.local.json.lock`` identified in the Task 5 implementation
note. The argparse-mutex bundle tests via a real subprocess call to ``cortex
init --ensure --update``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from cortex_command.init import scaffold
from cortex_command.init.handler import _run_ensure, main as init_main
from cortex_command.init.install_state import (
    INSTALL_MARKER_STALE_SECONDS,
    install_in_progress_marker_path,
)
from cortex_command.init.scaffold import ScaffoldError


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    """Initialize ``path`` as a git repo."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point HOME at a fresh directory under ``tmp_path`` with ``.claude``."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def _make_ensure_args(path: Path) -> argparse.Namespace:
    """Build a minimal Namespace for ``--ensure`` dispatch."""
    return argparse.Namespace(
        path=str(path),
        update=False,
        force=False,
        unregister=False,
        ensure=True,
    )


def _make_update_args(path: Path) -> argparse.Namespace:
    """Build a Namespace for the terminal ``cortex init --update`` path.

    Used to plant a real marker-present ``cortex/`` as a test precondition,
    since #273 removed in-session ``--ensure`` clean-repo bootstrap. The
    terminal ``--update`` path scaffolds + writes the marker (and the
    ``~/.claude/`` grant, harmless under an isolated HOME).
    """
    return argparse.Namespace(
        path=str(path),
        update=True,
        force=False,
        unregister=False,
        ensure=False,
    )


def _write_marker(
    repo_root: Path,
    *,
    init_artifacts_hash: str | None = None,
    cortex_version: str | None = "1.0.0",
) -> Path:
    """Write a ``.cortex-init`` JSON marker under ``cortex/`` with the given fields."""
    cortex_dir = repo_root / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    marker_path = cortex_dir / ".cortex-init"
    data: dict = {}
    if cortex_version is not None:
        data["cortex_version"] = cortex_version
    if init_artifacts_hash is not None:
        data["init_artifacts_hash"] = init_artifacts_hash
    data["initialized_at"] = "2024-01-01T00:00:00+00:00"
    marker_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return marker_path


def _fresh_install_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Create a fresh (current-timestamp) install-in-progress marker.

    Redirects XDG_STATE_HOME into ``tmp_path`` so the path is isolated per
    test.  Returns the marker path.
    """
    state_dir = tmp_path / "xdg-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    marker = install_in_progress_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b"")
    # Set mtime to now — fresh.
    now = time.time()
    os.utime(marker, (now, now))
    return marker


def _stale_install_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Create a stale (old-timestamp) install-in-progress marker."""
    state_dir = tmp_path / "xdg-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    marker = install_in_progress_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b"")
    stale_ts = time.time() - (INSTALL_MARKER_STALE_SECONDS + 10)
    os.utime(marker, (stale_ts, stale_ts))
    return marker


# ---------------------------------------------------------------------------
# R4 cases
# ---------------------------------------------------------------------------


def test_r4_case_i_marker_present_hash_match_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R4 case (i): marker-present + hash-match → no-op, no mtime change."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    # Suppress install-in-progress marker.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Plant a marker-present cortex/ via the terminal --update path (#273:
    # in-session --ensure no longer bootstraps a clean repo).
    rc = init_main(_make_update_args(repo))
    assert rc == 0
    marker_path = repo / "cortex" / ".cortex-init"
    assert marker_path.exists()
    mtime_before = marker_path.stat().st_mtime

    # Second invocation with same installed hash → no-op.
    rc2 = init_main(_make_ensure_args(repo))
    assert rc2 == 0
    mtime_after = marker_path.stat().st_mtime
    # The marker was not rewritten — mtime unchanged.
    assert mtime_before == mtime_after


def test_r4_case_ii_marker_present_hash_mismatch_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R4 case (ii): marker-present + hash-mismatch → refresh fires, drift reported."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Plant a marker-present cortex/ via the terminal --update path (#273:
    # in-session --ensure no longer bootstraps a clean repo).
    rc = init_main(_make_update_args(repo))
    assert rc == 0
    marker_path = repo / "cortex" / ".cortex-init"
    mtime_before = marker_path.stat().st_mtime

    # Simulate a CLI version bump: monkeypatch the installed hash to a mismatch.
    monkeypatch.setattr(
        scaffold,
        "_compute_init_artifacts_hash",
        lambda: "v1:" + "f" * 64,
    )

    # Taint a scaffold file so the drift report fires.
    (repo / "cortex" / "lifecycle" / "README.md").write_text(
        "DRIFT-SENTINEL\n", encoding="utf-8"
    )

    rc2 = init_main(_make_ensure_args(repo))
    assert rc2 == 0

    mtime_after = marker_path.stat().st_mtime
    # Marker was rewritten (mtime changed).
    assert mtime_after != mtime_before

    # Drift report emitted to stderr.
    captured = capsys.readouterr()
    assert "cortex/lifecycle/README.md" in captured.err or "--force" in captured.err


def test_r4_case_iii_a_clean_scratch_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R4 case (iii-a): marker-absent + no cortex/ → refuse, exit 2 (#273).

    In-session ``--ensure`` no longer bootstraps a clean repo; it refuses
    with a directive pointing the user to terminal ``cortex init`` and
    writes nothing (no ``cortex/``, ``CLAUDE.md``, or ``.gitignore``).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    assert not (repo / "cortex").exists()

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "not yet initialized" in captured.err

    # No new/modified files in the working tree.
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""
    assert not (repo / "cortex").exists()


def test_r4_case_iii_b_empty_cortex_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R4 case (iii-b): marker-absent + empty cortex/ → refuse, exit 2 (#273).

    Same refuse-with-directive behavior as (iii-a); the pre-existing empty
    ``cortex/`` dir is the only entry and it is left untouched.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Create an empty cortex/ dir.
    (repo / "cortex").mkdir()
    assert not any((repo / "cortex").iterdir())

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "not yet initialized" in captured.err

    # No marker was written; cortex/ is still empty.
    assert not (repo / "cortex" / ".cortex-init").exists()
    assert not any((repo / "cortex").iterdir())
    # An empty untracked dir is invisible to git status --porcelain, so no
    # new/modified tracked files appear either.
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""


def test_r4_case_iv_foreign_cortex_content_exit2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R4 case (iv): marker-absent + cortex/ has content → exit 2 + R19 diagnostic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    cortex_dir = repo / "cortex"
    cortex_dir.mkdir()
    (cortex_dir / "foreign-file.md").write_text("some content\n", encoding="utf-8")

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "cortex init" in captured.err or "pre-existing content" in captured.err


def test_r3_clean_repo_directive_distinct_from_refusal_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R3 distinctness gate: the clean-repo directive's unique marker substring
    (``"not yet initialized"``) is ABSENT from every sibling refusal message.

    Spec R3 (spec.md) requires the clean-repo case-(iii) directive to carry a
    unique substring NOT present in the R19 foreign-content message, "asserted
    against both messages in one test, so reusing the R19 text verbatim fails
    the gate." The existing case-(iii) tests assert only PRESENCE of the
    substring in clean-repo stderr; this regression test asserts its ABSENCE
    from the R19 decline and (spec-additive, per the plan) from both R8
    marker-corruption messages. If a future edit rewords the clean-repo
    directive to reuse any of those messages' phrasing, this test fails.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # --- Capture the clean-repo case-(iii) directive (the message under guard). ---
    repo_clean = tmp_path / "repo-clean"
    repo_clean.mkdir()
    _git_init(repo_clean)
    _isolate_home(monkeypatch, tmp_path)
    assert not (repo_clean / "cortex").exists()
    assert init_main(_make_ensure_args(repo_clean)) == 2
    clean_directive = capsys.readouterr().err
    # Sanity: the directive carries the unique marker substring (PRESENCE half,
    # mirroring the existing case-(iii) assertions).
    assert "not yet initialized" in clean_directive

    # --- R19 (foreign-content decline) message: capture via check_content_decline. ---
    repo_r19 = tmp_path / "repo-r19"
    cortex_dir = repo_r19 / "cortex"
    cortex_dir.mkdir(parents=True)
    (cortex_dir / "foreign.md").write_text("content\n", encoding="utf-8")
    with pytest.raises(ScaffoldError) as r19_exc:
        scaffold.check_content_decline(repo_r19)
    r19_message = str(r19_exc.value)
    # Sanity: this is the R19 message (its distinctive phrase).
    assert "pre-existing content" in r19_message

    # HARD GATE (spec R3): the clean-repo directive's unique marker substring
    # must NOT appear in the R19 message.
    assert "not yet initialized" not in r19_message

    # --- R8 message A: unparseable JSON → "reinitialize". Triggered via --ensure
    #     against a non-JSON marker (mirrors test_r8_bundle4_non_json_marker). ---
    repo_r8_json = tmp_path / "repo-r8-json"
    repo_r8_json.mkdir()
    _git_init(repo_r8_json)
    r8_json_cortex = repo_r8_json / "cortex"
    r8_json_cortex.mkdir(parents=True)
    (r8_json_cortex / ".cortex-init").write_text("this is not json\n", encoding="utf-8")
    assert init_main(_make_ensure_args(repo_r8_json)) == 2
    r8_unparseable_message = capsys.readouterr().err
    assert "unparseable" in r8_unparseable_message.lower()
    assert "not yet initialized" not in r8_unparseable_message

    # --- R8 message B: marker lacks cortex_version → "cortex init manually".
    #     Triggered via --ensure against a cortex_version-less marker (mirrors
    #     test_r8_bundle2_marker_without_cortex_version). ---
    repo_r8_ver = tmp_path / "repo-r8-ver"
    repo_r8_ver.mkdir()
    _git_init(repo_r8_ver)
    r8_ver_cortex = repo_r8_ver / "cortex"
    r8_ver_cortex.mkdir(parents=True)
    (r8_ver_cortex / ".cortex-init").write_text(
        json.dumps({"some_foreign_key": "value"}) + "\n", encoding="utf-8"
    )
    assert init_main(_make_ensure_args(repo_r8_ver)) == 2
    r8_version_message = capsys.readouterr().err
    assert "cortex_version" in r8_version_message
    assert "not yet initialized" not in r8_version_message


# ---------------------------------------------------------------------------
# Mutex error: --ensure --update rejected by argparse
# ---------------------------------------------------------------------------


def test_mutex_ensure_update_rejected() -> None:
    """``--ensure`` and ``--update`` are mutually exclusive at argparse time."""
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.cli", "init", "--ensure", "--update"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    # argparse emits 'not allowed with argument' or similar on mutex violations.
    combined = result.stderr + result.stdout
    assert (
        "not allowed" in combined
        or "mutually exclusive" in combined
        or "error" in combined.lower()
    )


# ---------------------------------------------------------------------------
# R6 cases: install-in-progress lock-check
# ---------------------------------------------------------------------------


def test_r6_bundle1_lock_timeout_exit2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R6 bundle 1: fresh marker held for full budget → exit 2 within 6s."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Plant a fresh install-in-progress marker.
    _fresh_install_marker(monkeypatch, tmp_path)

    start = time.monotonic()
    rc = init_main(_make_ensure_args(repo))
    elapsed = time.monotonic() - start

    assert rc == 2
    assert elapsed < 6.0, f"Lock-check exceeded 6s budget: {elapsed:.2f}s"

    captured = capsys.readouterr()
    assert "install in progress" in captured.err.lower() or "marker" in captured.err.lower()


def test_r6_bundle2_no_marker_proceeds_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6 bundle 2: no install-in-progress marker → proceeds normally."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Redirect XDG_STATE_HOME to a clean dir — no marker file present.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state-clean"))

    # Plant a marker-present cortex/ via terminal --update so --ensure
    # reaches the case-(i) no-op (#273: clean-repo --ensure now refuses).
    assert init_main(_make_update_args(repo)) == 0
    assert (repo / "cortex" / ".cortex-init").exists()

    rc = init_main(_make_ensure_args(repo))
    assert rc == 0
    assert (repo / "cortex" / ".cortex-init").exists()


def test_r6_bundle3_mid_poll_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6 bundle 3: marker present at t=0, cleared at t=2s → helper completes ok.

    Exercises the actual 50ms-poll loop: the marker is fresh when ``--ensure``
    starts polling, then cleared by a background timer at t≈2s.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Plant a marker-present cortex/ via terminal --update so --ensure reaches
    # the case-(i) no-op once the install lock clears (#273: clean-repo
    # --ensure now refuses). --update is the terminal path and is not subject
    # to the install lock-check, so it can run before the marker is planted.
    assert init_main(_make_update_args(repo)) == 0
    assert (repo / "cortex" / ".cortex-init").exists()

    marker = _fresh_install_marker(monkeypatch, tmp_path)

    # Schedule removal of the marker after 2 seconds.
    timer = threading.Timer(2.0, lambda: marker.unlink(missing_ok=True))
    timer.start()

    try:
        rc = init_main(_make_ensure_args(repo))
    finally:
        timer.cancel()

    assert rc == 0
    assert (repo / "cortex" / ".cortex-init").exists()


# ---------------------------------------------------------------------------
# R7 case: CORTEX_AUTO_ENSURE=0 silent no-op
# ---------------------------------------------------------------------------


def test_r7_cortex_auto_ensure_0_no_op(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7: CORTEX_AUTO_ENSURE=0 → exit 0, no writes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Seed with foreign content so --ensure would normally exit 2 if it ran.
    cortex_dir = repo / "cortex"
    cortex_dir.mkdir()
    (cortex_dir / "user-data.md").write_text("important user data\n", encoding="utf-8")

    monkeypatch.setenv("CORTEX_AUTO_ENSURE", "0")

    rc = init_main(_make_ensure_args(repo))
    assert rc == 0

    # No new files written — cortex/.cortex-init must not exist.
    assert not (repo / "cortex" / ".cortex-init").exists()
    # The foreign file is untouched.
    assert (cortex_dir / "user-data.md").exists()


# ---------------------------------------------------------------------------
# R8 cases: marker recovery / provenance discrimination
# ---------------------------------------------------------------------------


def test_r8_bundle1_truncated_marker_with_cortex_version_warning_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R8 bundle 1: truncated marker (cortex_version present, hash absent) → warning + refresh."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Write a pre-Phase-1 style marker: cortex_version only, no init_artifacts_hash.
    _write_marker(repo, init_artifacts_hash=None, cortex_version="1.2.3")

    rc = init_main(_make_ensure_args(repo))
    assert rc == 0

    captured = capsys.readouterr()
    # Warning about missing init_artifacts_hash must appear on stderr.
    assert "init_artifacts_hash" in captured.err

    # Marker must now be refreshed (init_artifacts_hash present).
    data = json.loads((repo / "cortex" / ".cortex-init").read_text(encoding="utf-8"))
    assert "init_artifacts_hash" in data


def test_r8_bundle2_marker_without_cortex_version_exit2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R8 bundle 2: marker without cortex_version → exit 2 foreign-artifact diagnostic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Write a marker with no cortex_version (foreign artifact).
    cortex_dir = repo / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    marker = cortex_dir / ".cortex-init"
    marker.write_text(
        json.dumps({"some_foreign_key": "value"}) + "\n", encoding="utf-8"
    )

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "cortex_version" in captured.err or "cortex marker" in captured.err.lower()


def test_r8_bundle3_malformed_cortex_version_exit2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R8 bundle 3: marker with malformed cortex_version → exit 2 foreign-artifact diagnostic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Write a marker with non-version cortex_version (does not match PEP 440 approx).
    cortex_dir = repo / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    marker = cortex_dir / ".cortex-init"
    marker.write_text(
        json.dumps({"cortex_version": "not-a-version", "initialized_at": "foo"}) + "\n",
        encoding="utf-8",
    )

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    # The absent-or-malformed → raise branch produces the foreign-artifact diagnostic.
    assert "cortex_version" in captured.err or "cortex marker" in captured.err.lower()


def test_r8_bundle4_non_json_marker_exit2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R8 bundle 4: non-JSON marker content → exit 2 unparseable JSON diagnostic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    cortex_dir = repo / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    (cortex_dir / ".cortex-init").write_text(
        "this is not json\n", encoding="utf-8"
    )

    rc = init_main(_make_ensure_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "unparseable" in captured.err.lower() or "json" in captured.err.lower()


def test_r8_bundle5_recovery_with_extra_cortex_content_refreshes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R8 bundle 5: cortex_version-only marker + existing cortex/ content → warning + refresh.

    Mirrors the real-world migration scenario: a previously-initialized cortex
    repo has accumulated content under cortex/ (backlog items, lifecycle dirs,
    etc.) and now hits the new --ensure flow with a pre-Phase-1 marker. The
    cortex_version discrimination at _read_marker_provenance() establishes
    prior cortex authorship, so R5 (scoped to marker-absent cases per spec.md:30)
    does not re-fire. Spec.md:66 anticipates this as the one-time migration
    storm and treats it as an accepted-cost transparent refresh.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    cortex_dir = repo / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)

    # Marker has cortex_version but NO init_artifacts_hash (R8 recovery path).
    _write_marker(repo, init_artifacts_hash=None, cortex_version="1.2.3")

    # cortex/ has accumulated content from prior cortex use (a real repo would
    # have cortex/backlog/, cortex/lifecycle/, etc.).
    (cortex_dir / "some-pre-existing.md").write_text(
        "pre-existing cortex-managed content\n", encoding="utf-8"
    )

    rc = init_main(_make_ensure_args(repo))
    assert rc == 0

    captured = capsys.readouterr()
    # Warning about missing init_artifacts_hash must appear on stderr.
    assert "init_artifacts_hash" in captured.err

    # Marker must now be refreshed (init_artifacts_hash present).
    data = json.loads((repo / "cortex" / ".cortex-init").read_text(encoding="utf-8"))
    assert "init_artifacts_hash" in data
    # Pre-existing content must remain untouched.
    assert (cortex_dir / "some-pre-existing.md").read_text(encoding="utf-8") == (
        "pre-existing cortex-managed content\n"
    )


# ---------------------------------------------------------------------------
# R1: no-``~/.claude/``-write spy + temp-HOME byte-identity (#273)
# ---------------------------------------------------------------------------


class _CallCounter:
    """Records the number of times it is invoked (settings_merge spy)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls += 1


def _install_settings_merge_spy(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, _CallCounter]:
    """Monkeypatch the three ``~/.claude/``-touching ``settings_merge`` calls.

    Returns the counters keyed by function name. ``register`` and
    ``unregister_matching_in_place`` were the post-dispatch grant + migration
    writes; ``validate_settings`` was the pre-flight read. #273 removed all
    three from ``--ensure`` — the counters prove they never fire.
    """
    counters = {
        "register": _CallCounter(),
        "validate_settings": _CallCounter(),
        "unregister_matching_in_place": _CallCounter(),
    }
    from cortex_command.init import settings_merge

    for name, counter in counters.items():
        monkeypatch.setattr(settings_merge, name, counter)
    return counters


def test_r1_ensure_makes_no_claude_settings_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R1: ``--ensure`` never calls register/validate_settings/unregister.

    Exercises the cases that previously reached the post-dispatch
    ``register``/``unregister`` block — case (ii) marker-present + hash-mismatch
    (refresh), case (iii) marker-absent + clean (refuse), and case (v) R8
    recovery — plus the case (i) early-return and case (iv) R19 decline. All
    three ``settings_merge`` calls must register zero invocations. Cases (ii)
    and (v) are exercised (not only the early-return case (i)) so the
    post-dispatch assertion is non-trivial.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # --- case (ii): marker-present + hash-mismatch → refresh ---
    repo_ii = tmp_path / "repo-ii"
    repo_ii.mkdir()
    _git_init(repo_ii)
    _isolate_home(monkeypatch, tmp_path)
    assert init_main(_make_update_args(repo_ii)) == 0  # plant marker via --update
    counters = _install_settings_merge_spy(monkeypatch)
    monkeypatch.setattr(
        scaffold, "_compute_init_artifacts_hash", lambda: "v1:" + "f" * 64
    )
    assert init_main(_make_ensure_args(repo_ii)) == 0
    # register / unregister_matching_in_place were post-dispatch; they ran on
    # case (ii) before #273. Now zero.
    assert counters["register"].calls == 0
    assert counters["unregister_matching_in_place"].calls == 0
    # validate_settings was a pre-flight call on every non-early path; zero too.
    assert counters["validate_settings"].calls == 0

    # --- case (v): R8 recovery (cortex_version-only marker) → refresh ---
    repo_v = tmp_path / "repo-v"
    repo_v.mkdir()
    _git_init(repo_v)
    _write_marker(repo_v, init_artifacts_hash=None, cortex_version="1.2.3")
    counters_v = _install_settings_merge_spy(monkeypatch)
    assert init_main(_make_ensure_args(repo_v)) == 0
    assert counters_v["register"].calls == 0
    assert counters_v["unregister_matching_in_place"].calls == 0
    assert counters_v["validate_settings"].calls == 0

    # --- case (iii): marker-absent + clean → refuse (exit 2) ---
    repo_iii = tmp_path / "repo-iii"
    repo_iii.mkdir()
    _git_init(repo_iii)
    counters_iii = _install_settings_merge_spy(monkeypatch)
    assert init_main(_make_ensure_args(repo_iii)) == 2
    assert counters_iii["register"].calls == 0
    assert counters_iii["unregister_matching_in_place"].calls == 0
    # validate_settings was pre-flight on every non-early path; on a refuse it
    # must also be zero (the refuse raises before any post-dispatch block, but
    # validate_settings is the pre-flight read removed by #273).
    assert counters_iii["validate_settings"].calls == 0

    # --- case (i): marker-present + hash-match → early return (no-op) ---
    repo_i = tmp_path / "repo-i"
    repo_i.mkdir()
    _git_init(repo_i)
    assert init_main(_make_update_args(repo_i)) == 0  # plant matching marker
    counters_i = _install_settings_merge_spy(monkeypatch)
    assert init_main(_make_ensure_args(repo_i)) == 0
    # validate_settings was a PRE-FLIGHT call reached on every non-early path —
    # assert zero on the early-return case (i) too.
    assert counters_i["validate_settings"].calls == 0
    assert counters_i["register"].calls == 0
    assert counters_i["unregister_matching_in_place"].calls == 0

    # --- case (iv): marker-absent + foreign content → R19 decline (exit 2) ---
    repo_iv = tmp_path / "repo-iv"
    repo_iv.mkdir()
    _git_init(repo_iv)
    (repo_iv / "cortex").mkdir()
    (repo_iv / "cortex" / "foreign.md").write_text("x\n", encoding="utf-8")
    counters_iv = _install_settings_merge_spy(monkeypatch)
    assert init_main(_make_ensure_args(repo_iv)) == 2
    # validate_settings (pre-flight) zero on the R19 decline path too.
    assert counters_iv["validate_settings"].calls == 0
    assert counters_iv["register"].calls == 0
    assert counters_iv["unregister_matching_in_place"].calls == 0


def test_r1_ensure_temp_home_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1: ``~/.claude/settings.local.json`` is byte-identical after ``--ensure``.

    Uses a marker-present drifted repo (case (ii)) so dispatch reaches the
    post-dispatch block — the site that wrote the ``~/.claude/`` grant before
    #273. Captures the settings file bytes (or its absence) before ``--ensure``
    and asserts they are unchanged afterward. ALSO asserts the sibling lockfile
    ``~/.claude/.settings.local.json.lock`` is never created: today
    ``validate_settings`` → ``_acquire_lock`` creates it, so its absence is a
    fixture-independent signal that no ``~/.claude/`` access occurred (the
    bytes-absent check alone is fixture-dependent — ``_isolate_home``
    pre-creates ``~/.claude/``, so "still absent" can pass trivially).
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    fake_home = _isolate_home(monkeypatch, tmp_path)

    # Plant a marker-present cortex/ via terminal --update (which legitimately
    # writes the grant under the isolated HOME), then capture the post-update
    # baseline so the byte-identity assertion targets --ensure's behavior only.
    assert init_main(_make_update_args(repo)) == 0

    settings_path = fake_home / ".claude" / "settings.local.json"
    lockfile_path = fake_home / ".claude" / ".settings.local.json.lock"
    before = settings_path.read_bytes() if settings_path.exists() else None

    # The terminal --update baseline legitimately acquired the lock (creating
    # the sibling lockfile). Remove it so the post-`--ensure` assertion below
    # tests whether `--ensure` *re-creates* it — not whether `--update` left it.
    lockfile_path.unlink(missing_ok=True)

    # Force a hash mismatch so --ensure drives case (ii) → reaches post-dispatch.
    monkeypatch.setattr(
        scaffold, "_compute_init_artifacts_hash", lambda: "v1:" + "f" * 64
    )
    assert init_main(_make_ensure_args(repo)) == 0

    after = settings_path.read_bytes() if settings_path.exists() else None
    assert after == before, "--ensure must not modify ~/.claude/settings.local.json"

    # The sibling lockfile is only created by _acquire_lock (reached via the
    # removed validate_settings/register/unregister calls). Its absence is a
    # fixture-independent proof that --ensure touched nothing under ~/.claude/.
    assert not lockfile_path.exists(), (
        "--ensure must not create the ~/.claude/ settings lockfile"
    )


@pytest.mark.skipif(
    os.geteuid() == 0 or sys.platform == "win32",
    reason="chmod 0o500 ineffective for root / not portable on Windows",
)
def test_r8_bundle6_unwritable_cortex_exit_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R8 bundle 6: unwritable cortex/ → non-zero exit (exception) naming the path.

    The handler's exit-code contract (handler.py:24-38) maps PermissionError
    to exit 1 ("unexpected runtime failure") — the exception propagates out of
    ``_run`` / ``main()`` so the CLI exits 1 via Python's default unhandled-
    exception behaviour.  When called in-process, the PermissionError propagates
    out of ``init_main``.  The test catches it and verifies the exception message
    names the unwritable path, satisfying R8's "diagnostic naming the failure
    mode" acceptance criterion.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    # Plant a marker-present cortex/ via terminal --update so --ensure routes
    # to the case-(ii) refresh write rather than the case-(iii) clean-repo
    # refuse (#273: clean-repo --ensure now refuses before any write). A
    # forced hash mismatch makes --ensure attempt a refresh write into cortex/.
    assert init_main(_make_update_args(repo)) == 0
    cortex_dir = repo / "cortex"
    assert (cortex_dir / ".cortex-init").exists()

    monkeypatch.setattr(
        scaffold,
        "_compute_init_artifacts_hash",
        lambda: "v1:" + "f" * 64,
    )

    # Make the cortex/ directory read-only so the refresh write inside it fails.
    cortex_dir.chmod(0o500)

    try:
        with pytest.raises((PermissionError, OSError)) as exc_info:
            init_main(_make_ensure_args(repo))
        # The exception message must name the unwritable path (or a child of it).
        assert str(cortex_dir) in str(exc_info.value) or "cortex" in str(exc_info.value).lower()
    finally:
        # Restore permissions so tmp_path cleanup can succeed.
        cortex_dir.chmod(0o700)
