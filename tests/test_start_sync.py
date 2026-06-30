"""Argv / backend-routing / exit-2 coverage for ``cortex-lifecycle-start-sync``.

Monkeypatches ``subprocess.run`` to capture the exact ``cortex-update-item``
argv per ``--backend`` arm and asserts the pinned flag list (so the historic
``cortex-update-item <stem> …`` invocation is preserved byte-for-byte), with a
negative control per arm (the ``none``/external/empty arms make zero calls; a
non-``none`` phase makes the status call but NOT the lifecycle-slug call). The
exit-2 case stubs an exit-2 child and asserts ``main`` returns 2 with the
candidate stderr surfaced.
"""

from __future__ import annotations

import json

import pytest

from cortex_command.lifecycle import start_sync as ss
from cortex_command.lifecycle.start_sync import main

STATUS_CALL = [
    "cortex-update-item",
    "326-foo",
    "--status",
    "in_progress",
    "--session-id",
    "S1",
    "--lifecycle-phase",
    "research",
]
SLUG_CALL = ["cortex-update-item", "326-foo", "--lifecycle-slug", "my-slug"]


class _FakeResult:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


@pytest.fixture
def calls(monkeypatch):
    """Capture every ``subprocess.run`` argv; the child always exits 0.

    ``LIFECYCLE_SESSION_ID`` is unset so ``_telemetry.log_invocation``
    early-returns before its own ``git rev-parse`` shell-out — otherwise the
    global ``subprocess.run`` patch would record telemetry's git call too.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    recorded: list[list[str]] = []

    def _fake_run(args, capture_output=False, text=False, **kw):
        recorded.append(list(args))
        return _FakeResult(returncode=0)

    monkeypatch.setattr(ss.subprocess, "run", _fake_run)
    return recorded


def _argv(backend: str, backlog_file: str = "326-foo.md", phase: str = "none"):
    return [
        "--backend",
        backend,
        "--backlog-file",
        backlog_file,
        "--phase",
        phase,
        "--session-id",
        "S1",
        "--lifecycle-slug",
        "my-slug",
    ]


# ---------------------------------------------------------------------------
# cortex-backlog arm
# ---------------------------------------------------------------------------


def test_cortex_backlog_phase_none_emits_both_calls(calls, capsys):
    rc = main(_argv("cortex-backlog", phase="none"))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    # EXACT, ordered argv: status write-back then lifecycle-slug write-back.
    assert calls == [STATUS_CALL, SLUG_CALL]
    assert out["signal"] == "synced"
    assert out["calls"] == ["status", "lifecycle_slug"]


def test_cortex_backlog_non_none_phase_status_only(calls, capsys):
    rc = main(_argv("cortex-backlog", phase="research"))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert calls == [STATUS_CALL]
    # Negative control: a non-none phase makes NO lifecycle-slug call.
    assert not any("--lifecycle-slug" in c for c in calls)
    assert out["calls"] == ["status"]


# ---------------------------------------------------------------------------
# none arm
# ---------------------------------------------------------------------------


def test_none_backend_makes_zero_calls(calls, capsys):
    rc = main(_argv("none"))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    # Negative control: the none arm calls cortex-update-item zero times.
    assert calls == []
    assert out["signal"] == "skipped"
    assert out["backend"] == "none"


# ---------------------------------------------------------------------------
# external arm
# ---------------------------------------------------------------------------


def test_external_backend_makes_zero_local_calls(calls, capsys):
    rc = main(_argv("github"))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert calls == []  # negative control: no local cortex-update-item write
    assert out["signal"] == "external"
    assert out["backend"] == "github"


# ---------------------------------------------------------------------------
# empty --backlog-file
# ---------------------------------------------------------------------------


def test_empty_backlog_file_makes_zero_calls(calls, capsys):
    rc = main(_argv("cortex-backlog", backlog_file=""))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert calls == []
    assert out["signal"] == "no_backlog"


# ---------------------------------------------------------------------------
# exit-2 passthrough
# ---------------------------------------------------------------------------


def test_exit2_passthrough_returns_2_and_surfaces_candidates(monkeypatch, capsys):
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

    def _fake_run(args, capture_output=False, text=False, **kw):
        return _FakeResult(returncode=2, stderr="ambiguous slug: 326-a, 326-b\n")

    monkeypatch.setattr(ss.subprocess, "run", _fake_run)

    rc = main(_argv("cortex-backlog"))
    captured = capsys.readouterr()

    assert rc == 2
    # Candidate list surfaced on stderr; no JSON outcome on stdout for exit-2.
    assert "ambiguous slug: 326-a, 326-b" in captured.err
    assert captured.out == ""


# ---------------------------------------------------------------------------
# all five flags are required (Req 11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drop",
    ["--backend", "--backlog-file", "--phase", "--session-id", "--lifecycle-slug"],
)
def test_each_flag_is_required(drop):
    full = _argv("cortex-backlog")
    i = full.index(drop)
    pruned = full[:i] + full[i + 2 :]  # remove the flag and its value
    with pytest.raises(SystemExit):
        main(pruned)


# ---------------------------------------------------------------------------
# CLI contract — one compact JSON line on the synced path
# ---------------------------------------------------------------------------


def test_cli_emits_one_compact_json_line(calls, capsys):
    rc = main(_argv("cortex-backlog"))
    out = capsys.readouterr().out

    assert rc == 0
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert ", " not in out and ": " not in out  # compact separators
