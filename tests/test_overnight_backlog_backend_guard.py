"""Fail-closed overnight backlog-backend guard tests (#317, R5/R6/R11).

The unattended overnight runner must never execute against a backlog backend
other than ``cortex-backlog``. The structural enforcement is a shared first-
check helper invoked at the top of ``handle_prepare`` and ``handle_launch``
(``cortex_command.overnight.cli_handler``) that resolves the backend
**in-process** via ``resolve_backlog_backend`` and refuses anything ≠
``cortex-backlog`` with a ``backend_not_supported`` JSON error envelope and a
non-zero exit, BEFORE any selection or bootstrap.

This is the deliberate fail-direction asymmetry of R11: overnight fails
**closed** (it runs unattended with ``--dangerously-skip-permissions``), the
OPPOSITE of the interactive reader which fails **open**. This test is the
load-bearing regression catch — it configures a genuine non-local ``backlog:``
block and asserts the refusal, so a future fail-open DRY-merge (routing the
guard through the graceful reader) flips it red.

Each handler is exercised through :mod:`cortex_command.overnight.cli_handler`
directly (mirroring ``tests/test_cli_overnight_format_json.py`` /
``tests/test_cortex_overnight_security.py``). ``select_overnight_batch`` AND
``bootstrap_session`` are patched to raise so the positive short-circuit
assertion (R6) holds: on the refusal path NEITHER is reached.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from cortex_command.overnight import backlog as backlog_module
from cortex_command.overnight import cli_handler
from cortex_command.overnight import plan as plan_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_backlog_config(repo_path: Path, backend: str) -> None:
    """Write a ``cortex/lifecycle.config.md`` with a nested ``backlog:`` block.

    Produces a *genuine* non-local config (the path the resolver descends),
    not a string-presence stub, so the refusal assertion exercises real
    config resolution.
    """
    cortex_dir = repo_path / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    body = f"---\nbacklog:\n  backend: {backend}\n---\nbody\n"
    (cortex_dir / "lifecycle.config.md").write_text(body, encoding="utf-8")


def _boom_select(*args, **kwargs):
    raise AssertionError(
        "select_overnight_batch must not be reached on the refusal path"
    )


def _boom_bootstrap(*args, **kwargs):
    raise AssertionError(
        "bootstrap_session must not be reached on the refusal path"
    )


def _patch_select_and_bootstrap_to_raise(monkeypatch) -> None:
    """Patch BOTH select + bootstrap to raise if reached.

    Proves the guard short-circuits before either is called (R6). The
    handlers resolve these lazily as ``backlog_module.select_overnight_batch``
    and ``plan_module.bootstrap_session``, so patching the source modules is
    sufficient.
    """
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", _boom_select
    )
    monkeypatch.setattr(
        plan_module, "bootstrap_session", _boom_bootstrap
    )


def _prepare_args() -> argparse.Namespace:
    return argparse.Namespace(
        format="json",
        backlog_dir=None,
        time_limit_hours=6,
        batch_size_cap=5,
    )


def _launch_args() -> argparse.Namespace:
    return argparse.Namespace(
        format="json",
        backlog_dir=None,
        time_limit_hours=6,
        batch_size_cap=5,
    )


# ---------------------------------------------------------------------------
# Refusal path — non-local backend (R5 + R6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["github-issues", "jira", "none"])
def test_handle_prepare_refuses_non_local_backend(
    backend, tmp_path, capsys, monkeypatch
) -> None:
    """``handle_prepare`` refuses a non-``cortex-backlog`` backend.

    Asserts the ``backend_not_supported`` envelope + non-zero exit, that the
    configured backend name appears in the message, and that NEITHER selection
    nor bootstrap was reached (the patched fns would raise).
    """
    repo_path = tmp_path
    _write_backlog_config(repo_path, backend)
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda *a, **k: repo_path
    )
    _patch_select_and_bootstrap_to_raise(monkeypatch)

    rc = cli_handler.handle_prepare(_prepare_args())
    assert rc != 0, "refusal must exit non-zero"

    payload = json.loads(capsys.readouterr().out)
    assert payload.get("error") == "backend_not_supported"
    assert backend in payload.get("message", "")
    # R15 schema-floor is auto-stamped by _emit_json (no hand-added version).
    assert isinstance(payload.get("schema_version"), str)
    assert "version" not in payload


@pytest.mark.parametrize("backend", ["github-issues", "jira", "none"])
def test_handle_launch_refuses_non_local_backend(
    backend, tmp_path, capsys, monkeypatch
) -> None:
    """``handle_launch`` refuses a non-``cortex-backlog`` backend.

    Same contract as the prepare case: ``backend_not_supported`` envelope +
    non-zero exit, configured backend named, neither select nor bootstrap
    reached.
    """
    repo_path = tmp_path
    _write_backlog_config(repo_path, backend)
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda *a, **k: repo_path
    )
    _patch_select_and_bootstrap_to_raise(monkeypatch)

    rc = cli_handler.handle_launch(_launch_args())
    assert rc != 0, "refusal must exit non-zero"

    payload = json.loads(capsys.readouterr().out)
    assert payload.get("error") == "backend_not_supported"
    assert backend in payload.get("message", "")
    assert isinstance(payload.get("schema_version"), str)
    assert "version" not in payload


# ---------------------------------------------------------------------------
# Proceed path — absent backlog: block (fail-toward-default)
# ---------------------------------------------------------------------------

def _raise_selection_marker(*args, **kwargs):
    """Selection stub that raises a distinctive, catchable error.

    The handlers catch any selection ``Exception`` and convert it to a
    ``selection_failed`` envelope. Reaching that envelope is the observable
    proof the guard returned ``None`` and the handler proceeded *past* the
    backend check — it would otherwise have emitted ``backend_not_supported``
    and never invoked selection.
    """
    raise RuntimeError("selection-reached-marker")


def test_handle_prepare_absent_block_proceeds_to_selection(
    tmp_path, capsys, monkeypatch
) -> None:
    """An absent ``backlog:`` block resolves to ``cortex-backlog`` and proceeds.

    With no ``lifecycle.config.md`` the resolver returns the default, so the
    guard returns ``None`` and the handler reaches selection. The selection
    stub raises, which the handler catches and surfaces as a
    ``selection_failed`` envelope — NOT ``backend_not_supported`` — proving the
    guard did not short-circuit.
    """
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda *a, **k: repo_path
    )
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", _raise_selection_marker
    )
    monkeypatch.setattr(
        plan_module, "bootstrap_session", _boom_bootstrap
    )

    rc = cli_handler.handle_prepare(_prepare_args())
    assert rc != 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get("error") == "selection_failed"
    assert "selection-reached-marker" in payload.get("message", "")


def test_handle_launch_absent_block_proceeds_to_selection(
    tmp_path, capsys, monkeypatch
) -> None:
    """Absent ``backlog:`` block → ``handle_launch`` proceeds past the guard.

    Same proof as the prepare case: the ``selection_failed`` envelope (not
    ``backend_not_supported``) is the observable evidence the guard did not
    refuse and selection was reached.
    """
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda *a, **k: repo_path
    )
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", _raise_selection_marker
    )
    monkeypatch.setattr(
        plan_module, "bootstrap_session", _boom_bootstrap
    )

    rc = cli_handler.handle_launch(_launch_args())
    assert rc != 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get("error") == "selection_failed"
    assert "selection-reached-marker" in payload.get("message", "")
