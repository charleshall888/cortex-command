"""Tests for cortex-lifecycle-branch-decision — the Implement §1 decision façade.

The composed reads (read_dispatch_choice / read_branch_mode / should_fire_picker /
_is_dirty_tree) are tested at their own sites; here we monkeypatch them to drive
the composition/routing seam and assert the discriminated ``state`` + payload.
"""

from __future__ import annotations

import json

import pytest

from cortex_command.lifecycle import branch_decision as bd


@pytest.fixture
def on_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bd, "_current_branch", lambda root: "main")


def _patch(monkeypatch, *, choice=None, mode=None, fire=(False, "suppressed"),
           dirty=False, worktree_cli=True):
    monkeypatch.setattr(bd, "read_dispatch_choice", lambda p: choice)
    monkeypatch.setattr(bd, "read_branch_mode", lambda r: mode)
    monkeypatch.setattr(bd, "should_fire_picker", lambda r, s, m: fire)
    monkeypatch.setattr(bd, "_is_dirty_tree", lambda r: dirty)
    monkeypatch.setattr(bd.shutil, "which", lambda name: "/x" if worktree_cli else None)


def test_not_on_main_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bd, "_current_branch", lambda root: "feature/x")
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "skip"
    assert r["branch"] == "feature/x"


def test_dispatch_choice_trunk_resolved(on_main, monkeypatch) -> None:
    _patch(monkeypatch, choice="trunk")
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "resolved"
    assert r["branch_mode"] == "trunk"
    assert r["entry_mode"] is None
    assert r["source"] == "dispatch_choice"


def test_dispatch_choice_worktree_is_selected(on_main, monkeypatch) -> None:
    _patch(monkeypatch, choice="worktree-interactive")
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "resolved"
    assert r["entry_mode"] == "selected"


def test_dispatch_choice_feature_branch(on_main, monkeypatch) -> None:
    _patch(monkeypatch, choice="feature-branch")
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "resolved"
    assert r["branch_mode"] == "feature-branch"


def test_branch_mode_suppressed_worktree_is_suppressed(on_main, monkeypatch) -> None:
    # No plan-time choice; branch-mode config suppresses the picker.
    _patch(monkeypatch, choice=None, mode="worktree-interactive",
           fire=(False, "suppressed"))
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "resolved"
    assert r["source"] == "branch_mode"
    assert r["entry_mode"] == "suppressed"


def test_picker_fires_carries_rendering_guards(on_main, monkeypatch) -> None:
    _patch(monkeypatch, choice=None, mode=None,
           fire=(True, "branch_mode_unset_or_invalid"),
           dirty=True, worktree_cli=False)
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "prompt"
    assert r["reason"] == "branch_mode_unset_or_invalid"
    assert r["uncommitted_changes"] is True
    assert r["worktree_option_available"] is False


def test_wait_dispatch_choice_falls_through_to_picker(on_main, monkeypatch) -> None:
    # "wait" is not a valid mode -> fall through to branch-mode/picker path.
    _patch(monkeypatch, choice="wait", mode=None, fire=(True, "branch_mode_prompt"))
    r = bd.resolve_branch_decision("feat")
    assert r["state"] == "prompt"


def test_every_state_is_known(on_main, monkeypatch) -> None:
    seen = set()
    monkeypatch.setattr(bd, "_current_branch", lambda root: "feature/x")
    seen.add(bd.resolve_branch_decision("f")["state"])
    monkeypatch.setattr(bd, "_current_branch", lambda root: "main")
    _patch(monkeypatch, choice="trunk")
    seen.add(bd.resolve_branch_decision("f")["state"])
    _patch(monkeypatch, choice=None, fire=(True, "dirty_tree"))
    seen.add(bd.resolve_branch_decision("f")["state"])
    assert seen <= set(bd.KNOWN_STATES)
    assert seen == {"skip", "resolved", "prompt"}


def test_cli_emits_json(on_main, monkeypatch, capsys) -> None:
    _patch(monkeypatch, choice="trunk")
    rc = bd.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "resolved"
