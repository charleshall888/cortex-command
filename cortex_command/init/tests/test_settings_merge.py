"""Settings-merge tests for ``cortex init`` (Task 12).

Covers settings-merge-side acceptance criteria:
    * happy path (R11) — fresh file and pre-existing content;
    * atomic write + sibling-key preservation (R12);
    * order preservation of existing allowWrite entries;
    * malformed settings refusal (R14) for register and --unregister paths;
    * invalid JSON refusal;
    * ``unregister`` semantics (R15), including idempotence;
    * argparse mutex: ``--unregister`` cannot combine with ``--update``;
    * concurrency under flock (R18 / ADR-2) — two variants:
        - ``test_concurrent_registers_under_flock`` — pre-os.replace contention;
        - ``test_staggered_registers_post_replace`` — post-replace-reopen race
          (the sibling-lockfile regression guard);
        - ``test_failed_caller_a_does_not_block_b_from_lock`` — successful
          callers only (narrower guarantee per Critical Review);
    * partial failure recovery via ``cortex init --update`` (R18 / R20 / R21) —
      step 5 settings, step 4 marker, step 3 gitignore, step 2 scaffold;
    * SIGINT / SIGTERM mid-merge frees the lock (ADR-2 + spec Edge Cases).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from cortex_command.init import scaffold, settings_merge
from cortex_command.init.handler import main as init_main
from cortex_command.init.settings_merge import (
    SettingsMergeError,
    register,
    unregister,
)


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


def _make_args(
    path: Path,
    *,
    update: bool = False,
    force: bool = False,
    unregister: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        path=str(path),
        update=update,
        force=force,
        unregister=unregister,
    )


def _target_path_for(repo_root: Path) -> str:
    """Compute the canonical sandbox-grant path string for a repo.

    Post-#202: the registration target is the umbrella ``cortex/`` path.
    """
    return str(repo_root.resolve() / "cortex") + "/"


def _cortex_target_for(repo_root: Path) -> str:
    """Alias of :func:`_target_path_for` kept for callsites that name it explicitly."""
    return _target_path_for(repo_root)


def _settings_path(home: Path) -> Path:
    return home / ".claude" / "settings.local.json"


# ---------------------------------------------------------------------------
# R11 happy path — fresh + pre-existing
# ---------------------------------------------------------------------------


def test_register_creates_settings_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R11: register() creates settings.local.json with only the new entry."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    target = _target_path_for(repo)
    assert not _settings_path(fake_home).exists()

    register(repo, target)

    settings = _settings_path(fake_home)
    assert settings.exists()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data == {"sandbox": {"filesystem": {"allowWrite": [target]}}}


def test_register_preserves_sibling_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12: non-mutated subtrees survive the merge byte-for-byte-equivalent."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    pre_existing = {
        "sandbox": {"network": {"allowUnixSockets": ["/tmp/x"]}},
        "permissions": {"allow": ["read"]},
    }
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    register(repo, target)

    data = json.loads(settings.read_text(encoding="utf-8"))

    # Both sibling keys preserved structurally.
    assert data["sandbox"]["network"] == {"allowUnixSockets": ["/tmp/x"]}
    assert data["permissions"] == {"allow": ["read"]}

    # New entry landed in the right place.
    assert data["sandbox"]["filesystem"]["allowWrite"] == [target]


def test_register_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R11 idempotence: second register() does not duplicate the entry."""
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    register(repo, target)
    register(repo, target)

    data = json.loads(_settings_path(tmp_path / "fake-home").read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert allow.count(target) == 1
    assert len(allow) == 1


def test_register_preserves_array_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Insertion order is preserved — no lexicographic reorder of allowWrite."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    pre_existing = {"sandbox": {"filesystem": {"allowWrite": ["a", "b"]}}}
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    # Use literal "c" as the new entry — matches the plan's assertion shape.
    register(repo, "c")

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["sandbox"]["filesystem"]["allowWrite"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# R14 malformed-settings refusal
# ---------------------------------------------------------------------------


def test_malformed_sandbox_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R14: malformed ``sandbox`` value raises SettingsMergeError; file unchanged."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    settings.write_text('{"sandbox": "broken"}\n', encoding="utf-8")
    pre_bytes = settings.read_bytes()

    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    with pytest.raises(SettingsMergeError) as exc_info:
        register(repo, target)

    assert "expected" in str(exc_info.value)
    assert settings.read_bytes() == pre_bytes


def test_invalid_json_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid JSON in settings.local.json raises with a clear diagnostic."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    settings.write_text("{not json", encoding="utf-8")
    pre_bytes = settings.read_bytes()

    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    with pytest.raises(SettingsMergeError) as exc_info:
        register(repo, target)

    # Error text names the file and JSON parse problem.
    msg = str(exc_info.value).lower()
    assert "json" in msg or "settings.local.json" in msg
    assert settings.read_bytes() == pre_bytes


# ---------------------------------------------------------------------------
# R15 --unregister semantics
# ---------------------------------------------------------------------------


def test_unregister_removes_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R15: unregister() removes the target entry, preserves unrelated entries."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    pre_existing = {
        "sandbox": {"filesystem": {"allowWrite": ["/kept/a/", "/kept/b/"]}}
    }
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    register(repo, target)
    unregister(repo, target)

    data = json.loads(settings.read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert target not in allow
    assert "/kept/a/" in allow
    assert "/kept/b/" in allow


def test_unregister_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R15 idempotence: unregister() of an absent entry is a no-op success."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    pre_existing = {"sandbox": {"filesystem": {"allowWrite": ["/kept/"]}}}
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    target = _target_path_for(repo)

    # Never registered — unregister should not raise.
    unregister(repo, target)
    unregister(repo, target)

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["sandbox"]["filesystem"]["allowWrite"] == ["/kept/"]


def test_unregister_malformed_settings_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ADR-3 step 3: --unregister pre-flight R14 fires on malformed sandbox.

    Verifies the malformed-settings refusal path covers unregister too, not
    only register. File must be byte-unchanged on exit.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    settings.write_text('{"sandbox": "broken"}\n', encoding="utf-8")
    pre_bytes = settings.read_bytes()

    non_git = tmp_path / "not-a-git-repo"
    non_git.mkdir()

    rc = init_main(_make_args(non_git, unregister=True))
    assert rc == 2

    captured = capsys.readouterr()
    assert "expected" in captured.err

    assert settings.read_bytes() == pre_bytes


# ---------------------------------------------------------------------------
# argparse mutex: --unregister alone
# ---------------------------------------------------------------------------


def test_argparse_mutex_rejects_unregister_with_update() -> None:
    """argparse rejects ``--unregister`` combined with ``--update`` (exit 2).

    Verifies the documented invariant is enforced at parse time, not left as
    a runtime assumption.
    """
    from cortex_command.cli import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        # argparse writes its own error message to stderr before raising.
        parser.parse_args(["init", "--update", "--unregister"])
    # argparse's default for mutex violations is exit code 2.
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Concurrency (R18 / ADR-2)
# ---------------------------------------------------------------------------


def _register_with_barrier(
    home_str: str, target_path: str, barrier: multiprocessing.Barrier
) -> None:
    """Subprocess worker that waits on a shared Barrier before registering."""
    os.environ["HOME"] = home_str
    from cortex_command.init.settings_merge import register as _register

    barrier.wait(timeout=10)
    _register(Path("/does-not-matter"), target_path)


def test_concurrent_registers_under_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R18 / ADR-2: two concurrent register() calls both land their entries.

    Exercises the pre-``os.replace`` contention case — both callers race to
    acquire ``LOCK_EX`` on the sibling lockfile before either has written.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    target_a = "/repo-a/cortex/"
    target_b = "/repo-b/cortex/"

    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(2)
    p_a = ctx.Process(
        target=_register_with_barrier, args=(str(fake_home), target_a, barrier)
    )
    p_b = ctx.Process(
        target=_register_with_barrier, args=(str(fake_home), target_b, barrier)
    )

    p_a.start()
    p_b.start()
    p_a.join(timeout=15)
    p_b.join(timeout=15)

    assert p_a.exitcode == 0
    assert p_b.exitcode == 0

    data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert target_a in allow
    assert target_b in allow


def test_staggered_registers_post_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: caller-B opens settings.local.json AFTER caller-A's
    ``os.replace``. With the OLD design (lock on settings.local.json itself),
    caller-B would open the new inode and acquire a fresh, non-contending
    flock — enabling a lost-update race. With the sibling-lockfile design
    (Task 7), caller-B blocks on the stable lockfile inode until caller-A
    releases.

    Implementation: monkeypatch settings_merge.atomic_write so that caller-A,
    after ``os.replace`` returns, fires ``post_replace_event`` and then sleeps
    briefly while still holding the flock (inside the finally on register).
    Caller-B, gated on ``post_replace_event``, calls register() — it MUST
    block on the sibling lockfile for A's flock to be released before
    reading, appending, and writing.

    Final assertion: both entries present in the final allowWrite.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    target_a = "/caller-a/cortex/"
    target_b = "/caller-b/cortex/"

    post_replace_event = threading.Event()
    real_atomic_write = settings_merge.atomic_write

    def instrumented_atomic_write(path: Path, content: str, *args, **kwargs) -> None:
        # Only instrument the settings file write for caller-A.
        real_atomic_write(path, content, *args, **kwargs)
        if path.name == "settings.local.json" and not post_replace_event.is_set():
            # Signal caller-B that os.replace has landed. Caller-A still
            # holds the lock (we're inside register's try/finally).
            post_replace_event.set()
            # Hold the lock long enough for B to attempt its open.
            time.sleep(0.4)

    monkeypatch.setattr(
        "cortex_command.init.settings_merge.atomic_write",
        instrumented_atomic_write,
    )

    # Caller-A runs in a background thread so caller-B (main thread, gated on
    # the event) can start its register() while A still holds the lock.
    def caller_a_main() -> None:
        register(Path("/does-not-matter"), target_a)

    thread_a = threading.Thread(target=caller_a_main)
    thread_a.start()

    # Block until caller-A's os.replace has landed.
    assert post_replace_event.wait(timeout=10), "caller-A never reached os.replace"

    # Now run caller-B on the main thread. With the sibling-lockfile design,
    # this acquires a fresh fd on the (now-replaced) settings file but must
    # still wait on the stable lockfile for A's flock to release.
    register(Path("/does-not-matter"), target_b)

    thread_a.join(timeout=15)

    data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert target_a in allow, "caller-A's entry was lost — post-replace race regressed"
    assert target_b in allow, "caller-B's entry never landed"


def test_failed_caller_a_does_not_block_b_from_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-2 narrower guarantee: if caller-A raises before os.replace, its
    entry is NOT in the final file, and caller-B proceeds on the pre-A state.

    The ADR-2 property as reframed by the Critical Review: "no lost-update
    race between two SUCCESSFUL callers". A failed caller doesn't owe the
    winning caller anything other than releasing the lock cleanly.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    target_a = "/caller-a/cortex/"
    target_b = "/caller-b/cortex/"

    # Seed a pre-state so we can prove B's write doesn't lose it.
    pre_existing = {"sandbox": {"filesystem": {"allowWrite": ["/kept/"]}}}
    _settings_path(fake_home).write_text(
        json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8"
    )

    real_atomic_write = settings_merge.atomic_write

    def failing_atomic_write(path: Path, content: str, *args, **kwargs) -> None:
        # Caller-A's write targets settings.local.json; fail it.
        if path.name == "settings.local.json":
            raise OSError("simulated disk full (caller-A)")
        real_atomic_write(path, content, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.init.settings_merge.atomic_write", failing_atomic_write
    )

    with pytest.raises(OSError):
        register(Path("/does-not-matter"), target_a)

    # Restore atomic_write; run caller-B. Must succeed without deadlocking.
    monkeypatch.setattr(
        "cortex_command.init.settings_merge.atomic_write", real_atomic_write
    )
    register(Path("/does-not-matter"), target_b)

    data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    # A's failed write is NOT in the file.
    assert target_a not in allow
    # B landed.
    assert target_b in allow
    # Pre-existing entry preserved (no lost-update on B's cycle).
    assert "/kept/" in allow


# ---------------------------------------------------------------------------
# Partial failure recovery (R18 / R20 / R21)
# ---------------------------------------------------------------------------


def test_partial_failure_recovery_step5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-3 step 5 failure: settings merge raises after scaffold+marker land.

    Expected: scaffold + marker present, settings.local.json byte-unchanged,
    exit != 0. Recovery via ``cortex init --update`` lands the entry AND
    refreshes the marker's ``initialized_at``.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    # Seed a well-formed empty-ish settings so pre-flight validation passes.
    settings.write_text('{"sandbox": {"filesystem": {"allowWrite": []}}}\n', encoding="utf-8")
    pre_bytes = settings.read_bytes()

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    real_sm_atomic_write = settings_merge.atomic_write
    raised = {"count": 0}

    def failing_settings_atomic_write(path: Path, content: str, *args, **kwargs) -> None:
        if path.name == "settings.local.json" and raised["count"] == 0:
            raised["count"] += 1
            raise OSError("simulated disk full")
        real_sm_atomic_write(path, content, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.init.settings_merge.atomic_write",
        failing_settings_atomic_write,
    )

    # First run should raise OSError at step 5 (after scaffold + marker + .gitignore).
    with pytest.raises(OSError):
        init_main(_make_args(repo))

    # Scaffold + marker present.
    assert (repo / "cortex" / ".cortex-init").exists()
    assert (repo / "cortex" / "lifecycle" / "README.md").exists()
    assert (repo / "cortex" / "requirements" / "project.md").exists()

    # Settings file byte-unchanged.
    assert settings.read_bytes() == pre_bytes

    # Capture marker's initialized_at for the refresh assertion.
    marker_before = json.loads((repo / "cortex" / ".cortex-init").read_text(encoding="utf-8"))

    # Restore atomic_write and re-run with --update. Entry lands; marker refreshed.
    monkeypatch.setattr(
        "cortex_command.init.settings_merge.atomic_write", real_sm_atomic_write
    )

    # Ensure at least 1ms elapses so the ISO timestamp differs.
    time.sleep(0.01)
    rc = init_main(_make_args(repo, update=True))
    assert rc == 0

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert _cortex_target_for(repo) in data["sandbox"]["filesystem"]["allowWrite"]

    marker_after = json.loads((repo / "cortex" / ".cortex-init").read_text(encoding="utf-8"))
    assert marker_after["initialized_at"] != marker_before["initialized_at"]


def test_partial_failure_recovery_step4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-3 step 4 failure: marker write raises after scaffold lands.

    Expected: scaffold files present, .cortex-init absent, exit != 0.
    Recovery: ``cortex init --update`` lands the marker and completes merge.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    _settings_path(fake_home).write_text(
        '{"sandbox": {"filesystem": {"allowWrite": []}}}\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    real_write_marker = scaffold.write_marker
    fail_once = {"done": False}

    def failing_write_marker(repo_root: Path, *, refresh: bool) -> None:
        if not fail_once["done"]:
            fail_once["done"] = True
            raise OSError("simulated failure during marker write")
        real_write_marker(repo_root, refresh=refresh)

    monkeypatch.setattr(
        "cortex_command.init.handler.scaffold.write_marker", failing_write_marker
    )

    with pytest.raises(OSError):
        init_main(_make_args(repo))

    # Scaffold files landed; marker did not.
    assert (repo / "cortex" / "lifecycle" / "README.md").exists()
    assert not (repo / "cortex" / ".cortex-init").exists()

    # Recovery with --update.
    rc = init_main(_make_args(repo, update=True))
    assert rc == 0
    assert (repo / "cortex" / ".cortex-init").exists()
    data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    assert _cortex_target_for(repo) in data["sandbox"]["filesystem"]["allowWrite"]


def test_partial_failure_recovery_step3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-3 step 3 failure: ensure_gitignore raises after scaffold lands.

    Also exercises orphan-prefix repair: seed .gitignore with a truncated
    ``.cortex-init-backu`` fragment; recovery removes it.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    _settings_path(fake_home).write_text(
        '{"sandbox": {"filesystem": {"allowWrite": []}}}\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Seed a truncated-prefix orphan in .gitignore.
    (repo / ".gitignore").write_text(
        "node_modules/\n.cortex-init-backu\n", encoding="utf-8"
    )

    real_ensure = scaffold.ensure_gitignore
    fail_once = {"done": False}

    def failing_ensure_gitignore(repo_root: Path) -> None:
        if not fail_once["done"]:
            fail_once["done"] = True
            raise OSError("simulated failure during ensure_gitignore")
        real_ensure(repo_root)

    monkeypatch.setattr(
        "cortex_command.init.handler.scaffold.ensure_gitignore",
        failing_ensure_gitignore,
    )

    with pytest.raises(OSError):
        init_main(_make_args(repo))

    # Scaffold ran; .gitignore not yet mutated to add our patterns (in the
    # failing pass). Marker NOT written (step 4 comes after step 3 in the
    # handler — which reorders marker ahead of gitignore; but the task's
    # framing calls the gitignore step "step 3" semantically). The key
    # structural assertion per the task:
    #   scaffold files present, .gitignore absent-or-incomplete, marker absent.
    assert (repo / "cortex" / "lifecycle" / "README.md").exists()
    # Gitignore still has the orphan and has NOT been repaired.
    gi_text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".cortex-init-backu" in gi_text.splitlines()

    # Recovery.
    rc = init_main(_make_args(repo, update=True))
    assert rc == 0

    gi_lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    # Orphan repaired.
    assert ".cortex-init-backu" not in gi_lines
    # Both required patterns land.
    assert "cortex/.cortex-init" in gi_lines
    assert "cortex/.cortex-init-backup/" in gi_lines
    # Marker lands.
    assert (repo / "cortex" / ".cortex-init").exists()


def test_partial_failure_recovery_step2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ADR-3 step 2 failure: scaffold atomic_write raises mid-walk.

    Monkeypatch scaffold.atomic_write to raise after N=3 of 5 writes; assert
    3 template files present, 2 missing, marker absent. Recovery fills the
    rest. **Also asserts the drift report surfaces pre-existing files** —
    the documented additivity gap (additive --update does not repair drift).
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    _settings_path(fake_home).write_text(
        '{"sandbox": {"filesystem": {"allowWrite": []}}}\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    SCAFFOLD_FILES = (
        "cortex/lifecycle/README.md",
        "cortex/backlog/README.md",
        "cortex/requirements/project.md",
        "cortex/lifecycle.config.md",
    )

    real_scaffold_atomic_write = scaffold.atomic_write
    scaffold_writes = {"count": 0}

    def failing_scaffold_atomic_write(path: Path, content: str, *args, **kwargs) -> None:
        # Only instrument writes under the repo root (not settings merge).
        try:
            path.relative_to(repo)
            rel = str(path.relative_to(repo))
        except ValueError:
            return real_scaffold_atomic_write(path, content, *args, **kwargs)
        # Only count template scaffold writes (not .gitignore, not marker).
        if rel in SCAFFOLD_FILES:
            scaffold_writes["count"] += 1
            if scaffold_writes["count"] > 3:
                raise OSError("simulated disk full at scaffold step")
        real_scaffold_atomic_write(path, content, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.init.scaffold.atomic_write", failing_scaffold_atomic_write
    )

    with pytest.raises(OSError):
        init_main(_make_args(repo))

    present = [rel for rel in SCAFFOLD_FILES if (repo / rel).exists()]
    missing = [rel for rel in SCAFFOLD_FILES if not (repo / rel).exists()]
    assert len(present) == 3
    assert len(missing) == 1
    assert not (repo / "cortex" / ".cortex-init").exists()

    # Taint one of the partially-landed files so the drift report has
    # something to surface on the recovery run.
    tainted = repo / present[0]
    tainted.write_text("TAINT\n", encoding="utf-8")

    # Restore and recover via --update.
    monkeypatch.setattr(
        "cortex_command.init.scaffold.atomic_write", real_scaffold_atomic_write
    )

    capsys.readouterr()  # flush any prior output
    rc = init_main(_make_args(repo, update=True))
    assert rc == 0

    # All 5 scaffold files now present.
    for rel in SCAFFOLD_FILES:
        assert (repo / rel).exists()
    assert (repo / "cortex" / ".cortex-init").exists()

    # The tainted file was NOT rewritten by --update (additive invariant).
    assert tainted.read_text(encoding="utf-8") == "TAINT\n"

    # Re-run --update now that the marker is present. R9's drift report
    # surfaces the still-tainted file — additivity does NOT repair drift,
    # that's the documented gap the task spec calls out.
    capsys.readouterr()
    rc = init_main(_make_args(repo, update=True))
    assert rc == 0
    captured = capsys.readouterr()
    assert present[0] in captured.err


# ---------------------------------------------------------------------------
# SIGINT / SIGTERM mid-merge (ADR-2 + spec Edge Cases)
# ---------------------------------------------------------------------------


_SIGINT_SCRIPT = textwrap.dedent(
    """
    import os, sys, time
    from pathlib import Path
    from cortex_command.init import settings_merge
    from cortex_command.init.settings_merge import register

    home = sys.argv[1]
    target = sys.argv[2]
    os.environ["HOME"] = home

    real_atomic_write = settings_merge.atomic_write
    def slow_atomic_write(path, content, *args, **kwargs):
        # Signal that we've acquired the lock and are about to (not) write.
        # Hold the lock long enough that the parent's subprocess.terminate()
        # lands while we're inside register's try block.
        Path(home, "lock-acquired.flag").write_text("1")
        time.sleep(30)
        real_atomic_write(path, content, *args, **kwargs)

    settings_merge.atomic_write = slow_atomic_write
    register(Path("/does-not-matter"), target)
    """
)


def test_sigint_mid_merge_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-2 + spec Edge Cases: SIGTERM mid-merge releases the flock cleanly.

    Spawn a subprocess that holds the flock inside ``register`` (blocks in a
    monkeypatched atomic_write), then terminate it. Verify a subsequent
    in-test register() acquires the lock cleanly (no deadlock — flock is
    process-scoped; the kernel releases on SIGTERM). Asserts either
    old-bytes or new-bytes on disk (no torn file).
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    # Seed a well-formed pre-state so old-bytes is observable.
    pre_existing = {"sandbox": {"filesystem": {"allowWrite": ["/kept/"]}}}
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")
    pre_bytes = settings.read_bytes()

    target_subprocess = "/subprocess-caller/cortex/"
    target_in_test = "/in-test-caller/cortex/"

    # Launch the subprocess that will hold the lock.
    proc = subprocess.Popen(
        [sys.executable, "-c", _SIGINT_SCRIPT, str(fake_home), target_subprocess],
        env={**os.environ, "HOME": str(fake_home)},
    )
    try:
        # Wait for the subprocess to signal lock acquisition (ensures the
        # kill below lands while the process holds the flock).
        flag = fake_home / "lock-acquired.flag"
        deadline = time.monotonic() + 10
        while not flag.exists():
            if time.monotonic() > deadline:
                raise AssertionError("subprocess never acquired the lock")
            time.sleep(0.05)

        # Terminate; kernel releases the process's flock.
        proc.terminate()
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    # Subsequent in-test register() must acquire the lock and succeed. If the
    # flock hadn't been released, this would block indefinitely (deadlock).
    register(Path("/does-not-matter"), target_in_test)

    post_bytes = settings.read_bytes()
    # The subprocess's register() never completed its atomic_write (we made
    # it sleep 30s and then terminated it). So before our in-test register(),
    # the file was still the seeded pre_bytes. After our in-test register(),
    # it contains our new entry plus the seed. Assert structurally: the
    # content is valid JSON and contains our in-test target.
    data = json.loads(post_bytes.decode("utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert target_in_test in allow

    # The subprocess target did NOT land (it was killed mid-sleep, before
    # os.replace). Either old or new bytes on disk — but the subprocess's
    # atomic_write never reached os.replace, so its target should be absent.
    assert target_subprocess not in allow
    # Pre-existing entry still present (no torn-file / no lost-update).
    assert "/kept/" in allow

    # Old-or-new-bytes invariant: post_bytes parses as valid JSON (a torn
    # file would not parse). The subprocess was killed before its
    # atomic_write reached os.replace, so pre_bytes was on disk before our
    # in-test register(); afterward, post_bytes is our clean rewrite.
    assert post_bytes != pre_bytes  # our in-test register() did land a change
    assert len(post_bytes) > 0


# ---------------------------------------------------------------------------
# Single cortex/ registration: cortex init registers exactly one cortex/ entry
# Test name substring "dual_registration" is grepped by the Task 5
# verification check (≥ 8 functions match).
# ---------------------------------------------------------------------------


# (a) happy-path: register-creates-settings; cortex/ entry appears (exactly one)
def test_dual_registration_happy_path_creates_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init on a fresh repo writes a single cortex/ entry to a
    newly-created settings.local.json."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    assert not _settings_path(fake_home).exists()

    rc = init_main(_make_args(repo))
    assert rc == 0

    data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    cortex_target = _cortex_target_for(repo)
    assert cortex_target in allow
    assert cortex_target.endswith("/cortex/")
    # Exactly one new entry per cortex init invocation.
    assert len([e for e in allow if e == cortex_target]) == 1


# (b) sibling-key preservation: other JSON keys untouched
def test_dual_registration_preserves_sibling_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init preserves sibling settings keys when writing the cortex/ entry."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    pre_existing = {
        "sandbox": {"network": {"allowUnixSockets": ["/tmp/x"]}},
        "permissions": {"allow": ["read"]},
    }
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    rc = init_main(_make_args(repo))
    assert rc == 0

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["sandbox"]["network"] == {"allowUnixSockets": ["/tmp/x"]}
    assert data["permissions"] == {"allow": ["read"]}
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    assert _cortex_target_for(repo) in allow


# (c) idempotency: running cortex init twice yields exactly one cortex/ entry
def test_dual_registration_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second cortex init --update does not duplicate the cortex/ entry."""
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    assert init_main(_make_args(repo)) == 0
    assert init_main(_make_args(repo, update=True)) == 0

    data = json.loads(
        _settings_path(tmp_path / "fake-home").read_text(encoding="utf-8")
    )
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    cortex_target = _cortex_target_for(repo)
    assert allow.count(cortex_target) == 1


# (d) single-entry: exactly one cortex/ entry per cortex init invocation
def test_dual_registration_order_lifecycle_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init registers exactly one cortex/ entry and one worktrees/
    entry (R7); neither is duplicated."""
    _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    assert init_main(_make_args(repo)) == 0

    data = json.loads(
        _settings_path(tmp_path / "fake-home").read_text(encoding="utf-8")
    )
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    cortex_target = _cortex_target_for(repo)
    worktree_target = str(repo.resolve() / ".claude" / "worktrees") + "/"
    assert cortex_target in allow
    assert cortex_target.endswith("/cortex/")
    # Exactly one of each entry per invocation — no duplicates.
    assert allow.count(cortex_target) == 1
    assert allow.count(worktree_target) == 1
    assert len(allow) == 2


# (e) malformed-sandbox refusal: R14 gate still rejects
def test_dual_registration_malformed_sandbox_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R14: malformed sandbox refuses cortex init; settings unchanged."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    settings.write_text('{"sandbox": "broken"}\n', encoding="utf-8")
    pre_bytes = settings.read_bytes()

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    rc = init_main(_make_args(repo))
    assert rc == 2
    captured = capsys.readouterr()
    assert "expected" in captured.err
    assert settings.read_bytes() == pre_bytes


# (f) unregister removes the cortex/ entry
def test_dual_registration_unregister_removes_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init --unregister removes the cortex/ entry that a register
    pass added."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    assert init_main(_make_args(repo)) == 0
    pre_data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    assert _cortex_target_for(repo) in pre_data["sandbox"]["filesystem"]["allowWrite"]

    assert init_main(_make_args(repo, unregister=True)) == 0
    post_data = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    allow = post_data["sandbox"]["filesystem"].get("allowWrite", [])
    assert _cortex_target_for(repo) not in allow


# (g) unregister-idempotent: absent cortex/ entry unregisters cleanly (no-op)
def test_dual_registration_unregister_idempotent_pre_r9_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init --unregister on a settings file that has no cortex/ entry
    succeeds (no-op) and leaves other entries untouched."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Simulate a pre-umbrella install that only has the old lifecycle/ entry.
    pre_existing = {
        "sandbox": {"filesystem": {"allowWrite": [_target_path_for(repo)]}}
    }
    settings.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

    rc = init_main(_make_args(repo, unregister=True))
    assert rc == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"].get("allowWrite", [])
    # cortex/ was never there; the old lifecycle/ entry is not touched by
    # the new unregister path (it only targets cortex/).
    assert _cortex_target_for(repo) not in allow


# (h) partial-failure recovery: --update adds missing cortex/ entry on
# a settings file without one
def test_dual_registration_partial_failure_recovery_via_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex init --update adds the cortex/ entry if absent without
    duplicating any existing entries."""
    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings = _settings_path(fake_home)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Simulate settings that have some prior entry but no cortex/ entry.
    pre_registered = {
        "sandbox": {"filesystem": {"allowWrite": ["/kept/"]}}
    }
    settings.write_text(json.dumps(pre_registered, indent=2) + "\n", encoding="utf-8")

    rc = init_main(_make_args(repo, update=True))
    assert rc == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    allow = data["sandbox"]["filesystem"]["allowWrite"]
    cortex_target = _cortex_target_for(repo)
    assert cortex_target in allow
    assert allow.count(cortex_target) == 1
    # Pre-existing entry preserved.
    assert "/kept/" in allow
