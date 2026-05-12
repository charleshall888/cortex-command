"""Scaffold-side tests for ``cortex init`` (Task 11).

Covers the scaffold-side acceptance criteria: happy path (R4 + R5),
``--update`` additive semantics (R8), drift report (R9), ``--force``
backup (R10), marker decline (R6), symlink refusal (R13), submodule
refusal (R3), content-aware decline (R19), marker refresh (R20),
``--path`` retargeting (R7), ``.gitignore`` append idempotence, and
``--unregister`` on a non-git path (Ask-item resolution). Exercises a
subset of R18 aggregate.

Settings-merge tests (R11, R12, R14, concurrency, SIGINT) land separately
in Task 12's ``test_settings_merge.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.init import scaffold
from cortex_command.init.handler import main as init_main


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    """Initialize ``path`` as a git repo."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


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


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point HOME at a fresh directory under ``tmp_path`` with ``.claude``."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


SCAFFOLD_FILES = (
    "lifecycle/README.md",
    "backlog/README.md",
    "requirements/project.md",
    "lifecycle.config.md",
)


# ---------------------------------------------------------------------------
# Happy path (R4 + R5)
# ---------------------------------------------------------------------------


def test_happy_path_scaffolds_four_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R4 + R5: default invocation writes four templates + marker + gitignore."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    rc = init_main(_make_args(repo))
    assert rc == 0

    for rel in SCAFFOLD_FILES:
        dest = repo / rel
        assert dest.exists(), f"missing scaffold file {rel}"
        assert dest.stat().st_size > 0, f"empty scaffold file {rel}"

    marker = repo / ".cortex-init"
    assert marker.exists()
    marker_data = json.loads(marker.read_text(encoding="utf-8"))
    assert "cortex_version" in marker_data
    assert "initialized_at" in marker_data

    gitignore = repo / ".gitignore"
    assert gitignore.exists()
    gitignore_text = gitignore.read_text(encoding="utf-8")
    gitignore_lines = gitignore_text.splitlines()
    assert ".cortex-init" in gitignore_lines
    assert ".cortex-init-backup/" in gitignore_lines


# ---------------------------------------------------------------------------
# --update additive semantics (R8)
# ---------------------------------------------------------------------------


def test_update_preserves_user_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8: --update writes missing files and leaves existing files untouched."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo)) == 0

    project = repo / "requirements" / "project.md"
    project.write_text("USER-EDIT-SENTINEL\n", encoding="utf-8")
    backlog_readme = repo / "backlog" / "README.md"
    backlog_readme.unlink()

    assert init_main(_make_args(repo, update=True)) == 0

    assert "USER-EDIT-SENTINEL" in project.read_text(encoding="utf-8")
    assert backlog_readme.exists()
    assert backlog_readme.stat().st_size > 0


def test_update_emits_drift_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R9: --update prints drift report to stderr for edited files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo)) == 0
    capsys.readouterr()  # flush captured output from the initial scaffold

    (repo / "lifecycle" / "README.md").write_text(
        "DRIFT-TEST\n", encoding="utf-8"
    )

    assert init_main(_make_args(repo, update=True)) == 0

    captured = capsys.readouterr()
    assert "lifecycle/README.md" in captured.err
    assert "--force" in captured.err


def test_update_writes_marker_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R20 edge case: --update on a repo without a marker creates it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo, update=True)) == 0
    assert (repo / ".cortex-init").exists()
    for rel in SCAFFOLD_FILES:
        assert (repo / rel).exists()


def test_update_on_empty_repo_acts_like_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8 + R20: --update on a completely empty repo produces the full scaffold."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo, update=True)) == 0

    for rel in SCAFFOLD_FILES:
        assert (repo / rel).exists()
    assert (repo / ".cortex-init").exists()
    assert (repo / ".gitignore").exists()


# ---------------------------------------------------------------------------
# --force backup (R10)
# ---------------------------------------------------------------------------


def test_force_backs_up_existing_with_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10: --force copies each existing file into a timestamped backup dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo)) == 0

    project = repo / "requirements" / "project.md"
    project.write_text("FORCE-BACKUP-SENTINEL\n", encoding="utf-8")

    assert init_main(_make_args(repo, force=True)) == 0

    backup_root = repo / ".cortex-init-backup"
    assert backup_root.is_dir()
    backup_entries = list(backup_root.iterdir())
    assert len(backup_entries) >= 1
    timestamped = backup_entries[0]
    backup_project = timestamped / "requirements" / "project.md"
    assert backup_project.exists()
    assert "FORCE-BACKUP-SENTINEL" in backup_project.read_text(encoding="utf-8")

    # The live file was overwritten with the shipped template content.
    assert "FORCE-BACKUP-SENTINEL" not in project.read_text(encoding="utf-8")

    gitignore_text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".cortex-init-backup/" in gitignore_text.splitlines()
    assert gitignore_text.endswith("\n")


def test_force_overwrites_no_marker_populated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R19 does NOT fire on --force: user explicitly asked for overwrite."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    lifecycle_dir = repo / "lifecycle"
    lifecycle_dir.mkdir()
    unrelated = lifecycle_dir / "unrelated.md"
    unrelated.write_text("pre-existing content\n", encoding="utf-8")

    assert init_main(_make_args(repo, force=True)) == 0

    for rel in SCAFFOLD_FILES:
        assert (repo / rel).exists()
    assert (repo / ".cortex-init").exists()
    # Force did not touch unrelated.md (it wasn't a scaffold target).
    assert unrelated.exists()


# ---------------------------------------------------------------------------
# Marker decline (R6)
# ---------------------------------------------------------------------------


def test_marker_decline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R6: second default invocation exits 2 with 'already initialized'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo)) == 0
    capsys.readouterr()

    rc = init_main(_make_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "already initialized" in captured.err


# ---------------------------------------------------------------------------
# Content-aware decline (R19)
# ---------------------------------------------------------------------------


def test_content_aware_decline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R19: default invocation refuses on populated non-marker repos.

    Asserts settings.local.json is byte-for-byte unchanged.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    fake_home = _isolate_home(monkeypatch, tmp_path)

    settings_path = fake_home / ".claude" / "settings.local.json"
    settings_path.write_text(
        '{"sandbox": {"filesystem": {"allowWrite": ["/pre-existing/"]}}}\n',
        encoding="utf-8",
    )
    pre_bytes = settings_path.read_bytes()

    cortex_dir = repo / "cortex"
    cortex_dir.mkdir()
    (cortex_dir / "unrelated.md").write_text(
        "user content\n", encoding="utf-8"
    )

    rc = init_main(_make_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "pre-existing content" in captured.err

    # No scaffold files were written (cortex/unrelated.md persists,
    # but the scaffold targets are absent).
    assert not (repo / "backlog" / "README.md").exists()
    assert not (repo / "requirements" / "project.md").exists()
    assert not (repo / "lifecycle.config.md").exists()
    assert not (repo / ".cortex-init").exists()

    # Settings file unchanged byte-for-byte.
    assert settings_path.read_bytes() == pre_bytes


# ---------------------------------------------------------------------------
# Symlink refusal (R13)
# ---------------------------------------------------------------------------


def test_symlink_refusal_prefix_aliased_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R13: refuse when lifecycle/ resolves outside the repo.

    Covers the ``/tmp/repo`` vs ``/tmp/repository`` false-positive case —
    ``is_relative_to`` must be used (not ``str.startswith``). The parent
    ``tmp_path`` contains both ``repo`` and ``repository`` directories; an
    escape symlink from ``repo/lifecycle`` points into
    ``repository`` (sibling, NOT a subpath of ``repo``). The previous
    ``str.startswith`` approach would false-positive (since
    ``/tmp/.../repository/escape`` starts with ``/tmp/.../repo``); the
    correct ``is_relative_to`` semantics catches the escape.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Sibling that shares a prefix — this is the failure mode
    # ``str.startswith`` would miss.
    sibling = tmp_path / "repository"
    sibling.mkdir()
    escape_target = sibling / "escape"
    escape_target.mkdir()

    fake_home = _isolate_home(monkeypatch, tmp_path)
    settings_path = fake_home / ".claude" / "settings.local.json"
    settings_path.write_text(
        '{"sandbox": {"filesystem": {"allowWrite": []}}}\n', encoding="utf-8"
    )
    pre_bytes = settings_path.read_bytes()

    (repo / "lifecycle").symlink_to(escape_target)

    rc = init_main(_make_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "outside the repo" in captured.err

    # Settings file unchanged byte-for-byte (R13 fires before merge).
    assert settings_path.read_bytes() == pre_bytes


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="APFS case-folding is macOS-specific",
)
def test_symlink_refusal_case_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R13: case-variant escape is still caught (macOS / APFS case-folding).

    On case-insensitive filesystems a sibling ``REPO`` would compare
    equal to ``repo`` under ``os.path.normcase`` — we assert the escape
    path (``elsewhere``) is correctly refused regardless of case.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    _isolate_home(monkeypatch, tmp_path)

    (repo / "lifecycle").symlink_to(elsewhere)

    rc = init_main(_make_args(repo))
    assert rc == 2


# ---------------------------------------------------------------------------
# Submodule refusal (R3)
# ---------------------------------------------------------------------------


def test_submodule_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R3: refuse when invoked inside a submodule.

    Uses a monkeypatched ``subprocess.run`` to return a non-empty superproject
    working tree rather than wiring up a real submodule fixture. This is the
    approach the task spec calls out as "simpler and less fragile" than a real
    submodule fixture.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if (
            isinstance(cmd, list)
            and len(cmd) >= 3
            and cmd[:2] == ["git", "rev-parse"]
            and cmd[2] == "--show-superproject-working-tree"
        ):
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"{tmp_path}/parent\n", stderr=""
            )
        return real_run(cmd, *args, **kwargs)

    # Monkeypatch the handler's view of ``subprocess.run``.
    monkeypatch.setattr(
        "cortex_command.init.handler.subprocess.run", fake_run
    )

    rc = init_main(_make_args(repo))
    assert rc == 2

    captured = capsys.readouterr()
    assert "submodule" in captured.err


# ---------------------------------------------------------------------------
# --path retargets (R7)
# ---------------------------------------------------------------------------


def test_path_flag_retargets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7: --path <dir> scaffolds at <dir> regardless of cwd."""
    repo = tmp_path / "target-repo"
    repo.mkdir()
    _git_init(repo)

    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    _isolate_home(monkeypatch, tmp_path)

    assert init_main(_make_args(repo)) == 0

    for rel in SCAFFOLD_FILES:
        assert (repo / rel).exists()
    assert (repo / ".cortex-init").exists()

    # No scaffold output appeared under the unrelated cwd.
    assert not (unrelated_cwd / ".cortex-init").exists()


# ---------------------------------------------------------------------------
# Marker refresh (R20)
# ---------------------------------------------------------------------------


def test_marker_refresh_on_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R20: --update rewrites the marker with current cortex_version + timestamp."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Seed with an older marker to verify --update rewrites cortex_version.
    (repo / ".cortex-init").write_text(
        json.dumps({"cortex_version": "0.0.0", "initialized_at": "stale"}) + "\n",
        encoding="utf-8",
    )

    # Monkeypatch the installed version to simulate a post-upgrade run.
    def fake_version(name: str) -> str:
        if name == "cortex-command":
            return "9.9.9"
        raise LookupError(name)

    monkeypatch.setattr(
        "cortex_command.init.scaffold.importlib.metadata.version", fake_version
    )

    assert init_main(_make_args(repo, update=True)) == 0

    marker_data = json.loads((repo / ".cortex-init").read_text(encoding="utf-8"))
    assert marker_data["cortex_version"] == "9.9.9"
    assert marker_data["initialized_at"] != "stale"


# ---------------------------------------------------------------------------
# .gitignore append idempotence + orphan repair
# ---------------------------------------------------------------------------


def test_gitignore_append_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R4: .gitignore append is idempotent — both patterns appear exactly once."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Pre-populate .gitignore with the canonical patterns to exercise the
    # no-op branch of ensure_gitignore.
    (repo / ".gitignore").write_text(
        ".cortex-init\n.cortex-init-backup/\n", encoding="utf-8"
    )

    assert init_main(_make_args(repo)) == 0

    gitignore_text = (repo / ".gitignore").read_text(encoding="utf-8")
    lines = gitignore_text.splitlines()
    assert lines.count(".cortex-init") == 1
    assert lines.count(".cortex-init-backup/") == 1

    # Run again via --force: still no duplicates.
    assert init_main(_make_args(repo, force=True)) == 0
    lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".cortex-init") == 1
    assert lines.count(".cortex-init-backup/") == 1


def test_gitignore_orphan_prefix_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_gitignore removes ``.cortex-init-backu`` orphan and re-appends."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Pre-populate .gitignore with an orphan-prefix fragment from a prior
    # truncated append, plus a pre-existing user rule that must survive.
    (repo / ".gitignore").write_text(
        "node_modules/\n.cortex-init-backu\n", encoding="utf-8"
    )

    scaffold.ensure_gitignore(repo)

    text = (repo / ".gitignore").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "node_modules/" in lines
    assert ".cortex-init-backu" not in lines  # orphan removed
    assert ".cortex-init" in lines
    assert ".cortex-init-backup/" in lines


# ---------------------------------------------------------------------------
# Partial scaffold + --update recovery
# ---------------------------------------------------------------------------


def test_partial_scaffold_update_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Partial scaffold: --update fills missing files and drift reports tainted ones.

    Explicitly documents the known gap around additivity not repairing
    truncated files — the drift report surfaces them, but --update does
    not rewrite them. The user must run --force to reset.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _isolate_home(monkeypatch, tmp_path)

    # Monkeypatch scaffold.atomic_write to raise after writing 3 of the 4
    # template files (mirrors Task 12's partial_failure_recovery_step2,
    # scoped to scaffold only — no marker write reached).
    real_atomic_write = scaffold.atomic_write
    call_log: list[Path] = []

    def failing_atomic_write(path: Path, content: str, *args, **kwargs) -> None:
        # Only count template scaffold writes (not .gitignore, not backup).
        rel = str(path.relative_to(repo)) if path.is_absolute() and repo in path.parents else str(path)
        if any(rel == s or rel.startswith(s.rsplit("/", 1)[0] + "/") for s in SCAFFOLD_FILES):
            call_log.append(path)
            if len(call_log) > 3:
                raise OSError("simulated disk full")
        real_atomic_write(path, content, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.init.scaffold.atomic_write", failing_atomic_write
    )

    # First run: fails partway through the scaffold loop. Handler surfaces
    # the OSError as exit 1 (unexpected runtime error, not a gate failure).
    with pytest.raises(OSError):
        init_main(_make_args(repo))

    # Exactly 3 of the 4 template files landed.
    present = [rel for rel in SCAFFOLD_FILES if (repo / rel).exists()]
    missing = [rel for rel in SCAFFOLD_FILES if not (repo / rel).exists()]
    assert len(present) == 3
    assert len(missing) == 1
    # Marker never written (scaffold failed before step 4).
    assert not (repo / ".cortex-init").exists()

    # Capture the bytes of the existing files to prove --update leaves
    # them untouched.
    pre_update_snapshot = {rel: (repo / rel).read_bytes() for rel in present}

    # Restore normal atomic_write and retry with --update. The two missing
    # files should land, the three partially-written files stay untouched.
    monkeypatch.setattr(
        "cortex_command.init.scaffold.atomic_write", real_atomic_write
    )

    # Taint one of the existing files so the drift report has something to
    # surface on the --update recovery run.
    tainted_path = repo / present[0]
    tainted_path.write_text("TAINTED-SENTINEL\n", encoding="utf-8")
    pre_update_snapshot[present[0]] = tainted_path.read_bytes()

    capsys.readouterr()  # flush any prior output
    assert init_main(_make_args(repo, update=True)) == 0

    # Missing files now exist.
    for rel in missing:
        assert (repo / rel).exists()

    # The tainted file was NOT rewritten by --update (additive invariant).
    assert tainted_path.read_bytes() == pre_update_snapshot[present[0]]

    # Re-run --update now that the marker is present. R9's drift report
    # surfaces the still-tainted file (additivity does NOT repair drift —
    # that's the known gap this test pins down).
    capsys.readouterr()
    assert init_main(_make_args(repo, update=True)) == 0
    captured = capsys.readouterr()
    assert present[0] in captured.err
    # Tainted file still tainted (drift report is read-only; --force is
    # the repair path).
    assert tainted_path.read_bytes() == pre_update_snapshot[present[0]]


# ---------------------------------------------------------------------------
# --unregister on a non-git path (Ask-item resolution)
# ---------------------------------------------------------------------------


def test_unregister_accepts_non_git_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--unregister bypasses the R2/R3 git-repo gate (step-0 early-branch).

    Verifies that a caller can clean up a stale allowWrite entry for a
    repo directory that no longer is a git repo (e.g., after ``rm -rf``).
    """
    non_git = tmp_path / "not-a-git-repo"
    non_git.mkdir()

    fake_home = _isolate_home(monkeypatch, tmp_path)

    # Seed settings.local.json with an entry that would normally be
    # registered for this path.
    target_path = str(non_git.resolve() / "lifecycle" / "sessions") + "/"
    settings_path = fake_home / ".claude" / "settings.local.json"
    settings_path.write_text(
        json.dumps(
            {"sandbox": {"filesystem": {"allowWrite": [target_path]}}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    rc = init_main(_make_args(non_git, unregister=True))
    assert rc == 0

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert target_path not in data["sandbox"]["filesystem"]["allowWrite"]
