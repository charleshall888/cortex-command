"""Unit tests for cortex_command.lifecycle.wontfix_cli (the order-enforcing verb).

Test names embed ``archive`` so the spec's ``pytest ... -k archive`` selector
resolves. Backlog terminalization is exercised by monkeypatching the verb's
``subprocess.run`` binding (no real cortex-update-item dependency).
"""

import json
import re

import pytest

from cortex_command.lifecycle import wontfix_cli


# --- harness ----------------------------------------------------------------

class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_update_item(monkeypatch, returncode=0, stderr="", recorder=None):
    # Intercept ONLY cortex-update-item; delegate everything else (e.g. the
    # telemetry `git rev-parse` call) to the real subprocess.run so the patch
    # stays scoped to the backlog-terminalization step.
    real_run = wontfix_cli.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "cortex-update-item":
            if recorder is not None:
                recorder.append(cmd)
            return _FakeCompleted(returncode=returncode, stderr=stderr)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(wontfix_cli.subprocess, "run", fake_run)


def _make_lifecycle(root, slug, parent_uuid=None, parent_id=None, index=True, events_rows=None):
    d = root / "cortex" / "lifecycle" / slug
    d.mkdir(parents=True)
    (d / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in (events_rows or [])), encoding="utf-8"
    )
    if index:
        lines = ["---", f"feature: {slug}"]
        if parent_uuid is not None:
            lines.append(f"parent_backlog_uuid: {parent_uuid}")
        if parent_id is not None:
            lines.append(f"parent_backlog_id: {parent_id}")
        lines += ["artifacts: [research, spec, plan]", "---", ""]
        (d / "index.md").write_text("\n".join(lines), encoding="utf-8")
    return d


def _archive_dir(root, slug):
    return root / "cortex" / "lifecycle" / "archive" / slug


# --- archive: all four guard branches ---------------------------------------

def test_archive_untracked_dir_creates_archive_and_moves(tmp_path, monkeypatch):
    # The temp repo has NO pre-existing archive/ — exercises the mkdir(archive/) fix.
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    src = _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch)
    assert wontfix_cli.main(["feat", "--reason", "done"]) == 0
    assert not src.exists()
    assert _archive_dir(tmp_path, "feat").is_dir()


def test_archive_rerun_is_clean_no_op(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch)
    assert wontfix_cli.main(["feat", "--reason", "done"]) == 0
    assert wontfix_cli.main(["feat", "--reason", "done"]) == 0  # no-op
    log = _archive_dir(tmp_path, "feat") / "events.log"
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    wontfix_rows = [r for r in rows if r.get("event") == "feature_wontfix"]
    assert len(wontfix_rows) == 1  # no duplicate
    # No nesting.
    assert not (_archive_dir(tmp_path, "feat") / "feat").exists()


def test_archive_both_exist_errors_without_nesting(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat")
    _archive_dir(tmp_path, "feat").mkdir(parents=True)
    rc = wontfix_cli.main(["feat", "--reason", "x"])
    assert rc == 1
    assert not (_archive_dir(tmp_path, "feat") / "feat").exists()


def test_archive_neither_exists_is_unknown_slug_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    rc = wontfix_cli.main(["ghost", "--reason", "x"])
    assert rc == 1


# --- worktree resolution ----------------------------------------------------

def test_archive_worktree_without_env_refuses(tmp_path, monkeypatch):
    # Discriminating worktree case: no env override + cwd in a worktree
    # (.git is a gitdir-pointer FILE) -> refuse, do not move.
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/feat\n", encoding="utf-8")
    src = _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    monkeypatch.chdir(tmp_path)
    rc = wontfix_cli.main(["feat", "--reason", "x"])
    assert rc == 1
    assert src.exists()  # not moved


def test_archive_env_set_bypasses_worktree_guard(tmp_path, monkeypatch):
    # env override short-circuits the resolver -> the worktree guard does not fire.
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    (tmp_path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    src = _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch)
    assert wontfix_cli.main(["feat", "--reason", "x"]) == 0
    assert not src.exists()
    assert _archive_dir(tmp_path, "feat").is_dir()


# --- row contract -----------------------------------------------------------

def test_row_is_detector_compatible_and_template_exact(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch)
    assert wontfix_cli.main(["feat", "--reason", "no longer needed"]) == 0

    log = _archive_dir(tmp_path, "feat") / "events.log"
    text = log.read_text()
    assert text.endswith("\n")  # newline-terminated (concatenation guard)

    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    wontfix_rows = [r for r in rows if r.get("event") == "feature_wontfix"]
    assert len(wontfix_rows) == 1
    row = wontfix_rows[0]
    assert set(row) == {"ts", "event", "feature", "reason"}
    assert row["feature"] == "feat" and row["reason"] == "no longer needed"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", row["ts"])

    # Documented-template equality (default separators + key order) — pins the
    # private-helper coupling and the timestamp format.
    expected_line = json.dumps(
        {"ts": row["ts"], "event": "feature_wontfix", "feature": "feat", "reason": "no longer needed"}
    )
    assert expected_line in text

    # statusline substring grep target.
    assert '"feature_wontfix"' in text

    # detector -> complete.
    from cortex_command.common import detect_lifecycle_phase

    assert detect_lifecycle_phase(_archive_dir(tmp_path, "feat"))["phase"] == "complete"

    # A second append parses cleanly (proves the trailing newline).
    wontfix_cli._append_event_atomic(log, json.dumps({"event": "probe"}) + "\n")
    rows2 = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert rows2[-1] == {"event": "probe"}


# --- backlog terminalization ------------------------------------------------

def test_terminalize_uses_index_parent_uuid(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", parent_uuid="uuid-123", parent_id="329")
    calls = []
    _patch_update_item(monkeypatch, recorder=calls)
    assert wontfix_cli.main(["feat", "--reason", "x"]) == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "cortex-update-item"
    assert "uuid-123" in cmd  # prefers parent_backlog_uuid
    assert "--status" in cmd and cmd[cmd.index("--status") + 1] == "wontfix"


def test_traversal_slug_rejected_pre_move(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    called = []
    _patch_update_item(monkeypatch, recorder=called)
    rc = wontfix_cli.main(["../evil", "--reason", "x"])
    assert rc == 2  # usage-class rejection
    assert called == []  # no filesystem op, no terminalization


def test_ambiguous_backlog_propagates_exit_2(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch, returncode=2, stderr="candidates: a, b\n")
    rc = wontfix_cli.main(["feat", "--reason", "x"])
    assert rc == 2


def test_ad_hoc_lifecycle_no_parent_skips_terminalize(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", index=False)  # no index.md -> no parent
    calls = []
    _patch_update_item(monkeypatch, recorder=calls)
    assert wontfix_cli.main(["feat", "--reason", "x"]) == 0
    assert calls == []  # step (c) is a clean no-op


def test_zero_match_where_parent_expected_is_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    _patch_update_item(monkeypatch, returncode=1, stderr="Item not found\n")
    rc = wontfix_cli.main(["feat", "--reason", "x"])
    assert rc == 1


# --- fail-forward recovery --------------------------------------------------

def test_fail_forward_repairs_partial_run_on_reinvocation(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    src = _make_lifecycle(tmp_path, "feat", parent_uuid="u-1")
    calls = []
    _patch_update_item(monkeypatch, recorder=calls)

    # First run: the move succeeds (step a) but the append (step b) raises.
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(wontfix_cli, "_append_event_atomic", _boom)
    with pytest.raises(OSError):
        wontfix_cli.main(["feat", "--reason", "x"])

    # The lifecycle is archived (fail-forward never rolls the move back), but no
    # feature_wontfix row and no terminalization happened yet.
    assert not src.exists()
    assert _archive_dir(tmp_path, "feat").is_dir()
    log = _archive_dir(tmp_path, "feat") / "events.log"
    assert "feature_wontfix" not in log.read_text()
    assert calls == []

    # Re-invocation (real append) independently re-asserts each postcondition.
    monkeypatch.undo()
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _patch_update_item(monkeypatch, recorder=calls)
    assert wontfix_cli.main(["feat", "--reason", "x"]) == 0
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert any(r.get("event") == "feature_wontfix" for r in rows)
    assert len(calls) == 1  # terminalized on the repair run
