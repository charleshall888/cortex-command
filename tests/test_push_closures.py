"""Tests for cortex-morning-review-push-closures — the verb that makes
morning-review walkthrough §6b's ticket closures durable.

Every test runs against a real fixture git repo (bare ``origin`` + clone) and
drives the real ``close_tickets`` verb to produce the ``changed_paths`` /
``status_changed`` inputs, rather than hand-writing them. That is deliberate:
the verb's whole contract is "stage what Task 9 reported, gate on what Task 9
observed", so a stubbed input would test the stub. It also means these tests
fail if the Task 9 contract drifts underneath the verb.

The fixture's remote is deliberately left unmoved (``behind == 0``) in the
happy path — that is the dominant Phase 4 case, and the one that defeats a
push delegated to ``cortex-git-sync-rebase`` (which returns at
``if behind == 0: return 0`` long before its ``git push``).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.overnight import close_tickets as ct
from cortex_command.overnight import push_closures as pc
from tests.conftest import make_item


@pytest.fixture(autouse=True)
def _git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every git subprocess — including the ones inside the verb — a
    deterministic identity and no gpg signing.

    The verb shells out with the ambient environment, so a developer's global
    ``commit.gpgsign = true`` would otherwise break the commit under test for
    reasons that have nothing to do with the code.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "3")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    monkeypatch.setenv("GIT_CONFIG_KEY_1", "tag.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", "false")
    monkeypatch.setenv("GIT_CONFIG_KEY_2", "core.editor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_2", "true")
    monkeypatch.delenv("GIT_DIR", raising=False)


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def _ahead(local: Path) -> int:
    """How many commits HEAD is ahead of origin/main, read independently of
    the verb's own helper."""
    out = _git("rev-list", "origin/main..HEAD", "--count", cwd=local).stdout
    return int(out.strip())


def _remote_text(remote: Path, path: str) -> str:
    """Read a file's content as it exists on the remote's main — the only
    direct evidence that a push landed."""
    return _git("show", f"main:{path}", cwd=remote).stdout


def _seed(tmp_path: Path, extra: str) -> tuple[Path, Path, Path]:
    """Build a bare origin + clone holding one committed backlog item.

    Returns (local, remote, item_path). The clone is left exactly at
    origin/main — the remote has not moved, so ``behind == 0``.
    """
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    local = tmp_path / "local"
    _git("clone", str(remote), str(local), cwd=tmp_path)

    backlog = local / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    item = make_item(backlog, "001-auth-api.md", "Auth API", extra=extra)

    _git("add", "cortex/backlog/001-auth-api.md", cwd=local)
    _git("commit", "-m", "Seed backlog item", cwd=local)
    _git("push", "origin", "main", cwd=local)
    return local, remote, item


def _close(local: Path) -> tuple[list[str], list[str]]:
    """Run the real §6b close and apply the walkthrough's documented mapping:
    --path is every changed_paths entry, --ticket is the id of each closed
    item whose status actually changed.
    """
    result = ct.close_tickets(
        [("auth-api", "001")], backend="cortex-backlog", project_root=local
    )
    closed = [e for e in result["results"] if e["state"] == "closed"]
    assert closed, result
    paths = [p for e in closed for p in e["changed_paths"]]
    tickets = [e["id"] for e in closed if e["status_changed"]]
    return paths, tickets


# ---------------------------------------------------------------------------
# (a) The happy path: a real status change is committed and pushed, and the
#     push is verified against the remote itself.
# ---------------------------------------------------------------------------


def test_real_status_change_is_committed_and_pushed(tmp_path: Path) -> None:
    """A genuine close reaches origin/main with the remote unmoved.

    This is the test that fails if the push is delegated to sync_rebase:
    behind == 0 here, so sync_rebase would short-circuit to exit 0 having
    pushed nothing, leaving ahead == 1 and the remote unchanged.
    """
    local, remote, item = _seed(tmp_path, extra="status: in_progress\n")
    assert _ahead(local) == 0, "fixture precondition: local starts at origin/main"

    paths, tickets = _close(local)
    assert paths == ["cortex/backlog/001-auth-api.md"]
    assert tickets == ["001"], "a real in_progress -> complete move must report a ticket"

    result = pc.push_closures(paths, tickets, project_root=local)

    assert result["state"] == "pushed", result
    assert result["committed"] is True
    assert result["pushed"] is True
    assert result["commit"]

    # Observation, not the verb's own word for it.
    assert _ahead(local) == 0
    assert "status: complete" in _remote_text(remote, "cortex/backlog/001-auth-api.md")
    assert "status: complete" in item.read_text()


def test_commit_subject_survives_the_repo_message_rules(tmp_path: Path) -> None:
    """The commit this verb writes has to pass the shared commit-msg hook:
    imperative, capitalized, no trailing period, subject <= 72 chars."""
    local, _remote, _item = _seed(tmp_path, extra="status: in_progress\n")
    paths, tickets = _close(local)
    pc.push_closures(paths, tickets, project_root=local)

    subject = _git("log", "-1", "--pretty=%s", cwd=local).stdout.strip()
    assert subject == "Close backlog ticket #001 after overnight merge"
    assert len(subject) <= 72
    assert not subject.endswith(".")
    assert subject[0].isupper()


def test_many_tickets_keep_the_subject_within_the_limit() -> None:
    """The named form is abandoned rather than allowed to overflow."""
    many = [f"{n:03d}" for n in range(1, 40)]
    subject = pc._commit_subject(many)
    assert len(subject) <= 72
    assert subject == "Close 39 backlog tickets after overnight merge"
    # ...but the ids are not lost — they move to the body.
    assert "#001" in pc._commit_message(many)
    assert "#039" in pc._commit_message(many)


# ---------------------------------------------------------------------------
# (b) The derivation: ahead-count 0 alone is not evidence of a push.
# ---------------------------------------------------------------------------


def test_noop_run_reports_no_push_despite_a_zero_ahead_count(tmp_path: Path) -> None:
    """Nothing was committed, so nothing was pushed — even though
    `git rev-list origin/main..HEAD --count` reads 0 at this exact moment.

    This is the guard against deriving `pushed` from the ahead-count alone:
    that reading is 0 both when a push landed and when no commit was ever
    made, so it cannot distinguish them. `pushed` also requires that HEAD
    moved.
    """
    local, _remote, _item = _seed(tmp_path, extra="status: in_progress\n")
    head_before = _git("rev-parse", "HEAD", cwd=local).stdout.strip()

    # The precondition that would fool an ahead-count-only derivation.
    assert _ahead(local) == 0

    result = pc.push_closures([], [], project_root=local)

    assert result["pushed"] is False, "no commit was made, so no push happened"
    assert result["committed"] is False
    assert result["state"] == "no-op"
    assert _git("rev-parse", "HEAD", cwd=local).stdout.strip() == head_before


def test_ticketed_run_that_commits_nothing_reports_no_push(tmp_path: Path) -> None:
    """The sharp edge of the same guard: the commit gate is satisfied, the
    verb runs all the way to the commit, and still no push is claimed.

    The no-op test above is short-circuited by the --ticket gate, so it cannot
    tell an ahead-count-only derivation from a correct one. This one can:
    tickets ARE given, so the gate passes and the verb reaches `git commit` —
    which finds nothing to record because the close is already committed and
    pushed. HEAD does not move, the ahead-count reads 0, and `pushed` must
    still be False. A derivation of `pushed = (ahead == 0)` reports a phantom
    push here.
    """
    local, _remote, _item = _seed(tmp_path, extra="status: in_progress\n")
    paths, tickets = _close(local)
    assert tickets == ["001"]

    # Someone already landed this exact close, leaving nothing to commit.
    _git("add", *paths, cwd=local)
    _git("commit", "-m", "Land the close out of band", cwd=local)
    _git("push", "origin", "main", cwd=local)
    head_before = _git("rev-parse", "HEAD", cwd=local).stdout.strip()
    assert _ahead(local) == 0, "the reading that would fool an ahead-only derivation"

    result = pc.push_closures(paths, tickets, project_root=local)

    assert result["pushed"] is False, (
        "HEAD never moved, so this verb pushed nothing — the zero ahead-count "
        "is someone else's push, not evidence of ours"
    )
    assert result["committed"] is False
    assert result["state"] == "error"
    assert _git("rev-parse", "HEAD", cwd=local).stdout.strip() == head_before


# ---------------------------------------------------------------------------
# (c) The churn gate: a redundant re-close writes a real diff and is skipped.
# ---------------------------------------------------------------------------


def test_redundant_reclose_creates_no_commit_and_no_push(tmp_path: Path) -> None:
    """The common case — the overnight write-back already set status:
    complete, so §6b's close only bumps `updated:`.

    The item is seeded already-complete with a stale `updated:` date, so the
    re-close produces a genuine, non-empty file diff whose only content is a
    timestamp. The verb is expected to leave it uncommitted rather than push
    timestamp noise to main every morning.
    """
    local, remote, item = _seed(
        tmp_path,
        extra="status: complete\nlifecycle_phase: complete\nupdated: 2020-01-01\n",
    )
    head_before = _git("rev-parse", "HEAD", cwd=local).stdout.strip()
    remote_before = _remote_text(remote, "cortex/backlog/001-auth-api.md")

    paths, tickets = _close(local)

    # The close really did rewrite the file — this test is not vacuous.
    assert paths == ["cortex/backlog/001-auth-api.md"]
    assert "updated: 2020-01-01" not in item.read_text()
    dirty = _git(
        "status", "--porcelain", "--", "cortex/backlog/001-auth-api.md", cwd=local
    ).stdout
    assert dirty.strip(), "the re-close must leave a real diff for the verb to skip"

    # ...but nothing meaningful moved, so the walkthrough's mapping yields no
    # --ticket, which is the commit gate.
    assert tickets == []

    result = pc.push_closures(paths, tickets, project_root=local)

    assert result["state"] == "no-op", result
    assert result["committed"] is False
    assert result["pushed"] is False
    assert _git("rev-parse", "HEAD", cwd=local).stdout.strip() == head_before
    assert _remote_text(remote, "cortex/backlog/001-auth-api.md") == remote_before


# ---------------------------------------------------------------------------
# (d) The push failure: a rejected non-fast-forward names the stranded ids.
# ---------------------------------------------------------------------------


def test_rejected_non_fast_forward_reports_the_unpushed_tickets(tmp_path: Path) -> None:
    """When the remote has moved, the close stays committed locally and the
    verb says plainly that it is not on main — naming the ids, never forcing.
    """
    local, remote, _item = _seed(tmp_path, extra="status: in_progress\n")

    # A second clone moves origin/main out from under `local`, which never
    # fetches — exactly the shape that rejects a push as non-fast-forward.
    other = tmp_path / "other"
    _git("clone", str(remote), str(other), cwd=tmp_path)
    (other / "unrelated.md").write_text("elsewhere\n")
    _git("add", "unrelated.md", cwd=other)
    _git("commit", "-m", "Move the remote", cwd=other)
    _git("push", "origin", "main", cwd=other)
    remote_head_before = _git("rev-parse", "main", cwd=remote).stdout.strip()

    paths, tickets = _close(local)
    assert tickets == ["001"]

    result = pc.push_closures(paths, tickets, project_root=local)

    assert result["state"] == "push-failed", result
    assert result["pushed"] is False
    assert result["committed"] is True, "the close is committed locally"
    assert result["unpushed_tickets"] == ["001"]
    assert "001" in result["message"]

    # The commit is real and local...
    assert "Close backlog ticket #001" in _git(
        "log", "-1", "--pretty=%s", cwd=local
    ).stdout
    # ...and the remote was not force-overwritten.
    assert _git("rev-parse", "main", cwd=remote).stdout.strip() == remote_head_before


# ---------------------------------------------------------------------------
# Scope: only the reported paths reach main.
# ---------------------------------------------------------------------------


def test_only_the_reported_paths_are_committed(tmp_path: Path) -> None:
    """A concurrent session's staged file must not ride along to main.

    This is why the commit is pathspec-limited rather than a bare `git commit`
    over the index: Task 9 exists to make the pushable set knowable, and a
    whole-index commit would discard that answer at the last step.
    """
    local, remote, _item = _seed(tmp_path, extra="status: in_progress\n")

    # Someone else's work, already staged in the index.
    (local / "concurrent.md").write_text("not mine to push\n")
    _git("add", "concurrent.md", cwd=local)

    paths, tickets = _close(local)
    result = pc.push_closures(paths, tickets, project_root=local)
    assert result["state"] == "pushed", result

    committed_files = _git(
        "show", "--name-only", "--pretty=", "HEAD", cwd=local
    ).stdout.split()
    assert committed_files == ["cortex/backlog/001-auth-api.md"]
    assert "concurrent.md" not in _git("ls-tree", "-r", "--name-only", "main", cwd=remote).stdout


# ---------------------------------------------------------------------------
# CLI contract.
# ---------------------------------------------------------------------------


def test_cli_emits_one_json_struct_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Errors are data on stdout, not a traceback and a non-zero exit."""
    import json

    monkeypatch.setattr(
        pc, "_resolve_user_project_root", lambda: tmp_path / "nonexistent"
    )
    rc = pc.main(["--path", "cortex/backlog/001-x.md", "--ticket", "001"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] in pc.KNOWN_STATES
    assert payload["pushed"] is False
