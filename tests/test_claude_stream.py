"""Subprocess-level tests for ``cortex_command.claude_stream`` (spec R3-R8, R11 spawn half).

Each test spawns ``tests/fixtures/fake_claude.py`` through the real seam.
Tests use ``asyncio.run()`` because pytest-asyncio is not a project dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import pytest

from cortex_command import claude_stream
from cortex_command.claude_stream import (
    ClaudeSpawnError,
    build_argv,
    build_env,
    run_claude,
)

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
KIB = 1024


def _argv(**flags):
    """Real build_argv output, run through this interpreter instead of a shebang."""
    return [sys.executable, str(FAKE_CLAUDE)] + build_argv("claude", **flags)[1:]


def _write_frames(path: Path, lines: list) -> Path:
    body = b"".join(
        (ln if isinstance(ln, bytes) else json.dumps(ln).encode()) + b"\n" for ln in lines
    )
    path.write_bytes(body)
    return path


def _run(argv, *, prompt="hi", env_extra=None, on_stderr=None, cwd=None):
    env = build_env({})
    env.update(env_extra or {})

    async def go():
        frames = []
        async with run_claude(argv, prompt=prompt, cwd=cwd, env=env, on_stderr=on_stderr) as run:
            async for frame in run.frames():
                frames.append(frame)
        return frames, run.exit_code

    return asyncio.run(go())


def test_argv_carries_every_flag_and_no_positional_prompt():
    argv = build_argv(
        "/bin/claude",
        max_turns=7,
        max_budget_usd=1.5,
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Edit", "Bash"],
        system_prompt="be terse",
        settings="/tmp/s.json",
        effort="high",
    )
    assert argv[:5] == ["/bin/claude", "-p", "--output-format", "stream-json", "--verbose"]
    pairs = dict(zip(argv[5::2], argv[6::2]))
    assert len(argv[5:]) == 2 * len(pairs), "every flag after the fixed prefix takes one value"
    assert pairs == {
        "--max-turns": "7",
        "--max-budget-usd": "1.5",
        "--permission-mode": "bypassPermissions",
        "--allowedTools": "Read,Edit,Bash",
        "--system-prompt": "be terse",
        "--settings": "/tmp/s.json",
        "--effort": "high",
    }
    for banned in ("--bare", "--input-format", "--model"):
        assert banned not in argv


def test_argv_omits_unset_flags():
    assert build_argv("claude") == ["claude", "-p", "--output-format", "stream-json", "--verbose"]


def test_large_prompt_arrives_byte_identical_on_stdin(tmp_path):
    prompt = "".join(chr(0x41 + i % 26) for i in range(200 * KIB)) + " é✓ end"
    echo = tmp_path / "stdin.bin"
    frames, code = _run(
        _argv(), prompt=prompt, env_extra={"FAKE_CLAUDE_ECHO_STDIN_TO": str(echo)}
    )
    assert code == 0
    assert echo.read_bytes() == prompt.encode("utf-8")
    assert len(echo.read_bytes()) > 128 * KIB


def test_single_256kib_assistant_line_parses(tmp_path):
    big = {"type": "assistant", "message": {"content": [{"type": "text", "text": "a" * (256 * KIB)}]}}
    frames_file = _write_frames(tmp_path / "f.ndjson", [big, {"type": "result", "is_error": False}])
    frames, code = _run(_argv(), env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file)})
    assert code == 0
    assert frames[0] == big
    assert frames[1]["type"] == "result"


def test_large_stderr_and_stdout_complete(tmp_path):
    lines = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "b" * 1000}]}}
        for _ in range(150)
    ] + [{"type": "result"}]
    frames_file = _write_frames(tmp_path / "f.ndjson", lines)
    assert frames_file.stat().st_size > 128 * KIB
    seen: list[str] = []
    frames, code = _run(
        _argv(),
        prompt="p" * (200 * KIB),
        env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file), "FAKE_CLAUDE_STDERR_BYTES": str(200 * KIB)},
        on_stderr=seen.append,
    )
    assert code == 0
    assert len(frames) == 151
    assert sum(len(s) + 1 for s in seen) >= 200 * KIB
    assert all(s == "x" * 999 for s in seen)


def test_raising_stderr_callback_does_not_stall_the_run(tmp_path):
    frames_file = _write_frames(tmp_path / "f.ndjson", [{"type": "result"}])

    def boom(_line):
        raise RuntimeError("callback bug")

    frames, code = _run(
        _argv(),
        env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file), "FAKE_CLAUDE_STDERR_BYTES": str(100 * KIB)},
        on_stderr=boom,
    )
    assert code == 0
    assert frames == [{"type": "result"}]


def test_env_keeps_parent_path_home_drops_claudecode_applies_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    overlay = {"CLAUDECODE": "", "TMPDIR": str(tmp_path), "CORTEX_REPO_ROOT": "/wt", "FOO_OVERLAY": "bar"}
    env = build_env(overlay)
    assert "CLAUDECODE" not in env
    env_dump = tmp_path / "env.json"
    env["FAKE_CLAUDE_ENV_TO"] = str(env_dump)

    async def go():
        async with run_claude(_argv(), prompt="x", cwd=None, env=env) as run:
            async for _ in run.frames():
                pass
        return run.exit_code

    assert asyncio.run(go()) == 0
    child_env = json.loads(env_dump.read_text())
    assert child_env["PATH"] == os.environ["PATH"]
    assert child_env["HOME"] == os.environ["HOME"]
    assert "CLAUDECODE" not in child_env
    for key, value in overlay.items():
        if key != "CLAUDECODE":
            assert child_env[key] == value

    monkeypatch.delenv("CLAUDECODE")
    assert "CLAUDECODE" not in build_env({})


def test_frame_after_result_is_yielded_and_run_ends_at_exit(tmp_path):
    lines = [
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False},
        {"type": "system", "subtype": "hook_response"},
    ]
    frames_file = _write_frames(tmp_path / "f.ndjson", lines)
    frames, code = _run(
        _argv(), env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file), "FAKE_CLAUDE_EXIT": "3"}
    )
    assert frames == lines
    assert code == 3


def test_malformed_lines_are_skipped_and_unknown_types_pass_through(tmp_path):
    lines = [
        b"",
        b"   ",
        b"not json at all",
        b"[1, 2, 3]",
        b'"a string"',
        {"no_type": True},
        {"type": 42},
        {"type": "never_seen_before", "x": 1},
        {"type": "result"},
    ]
    frames_file = _write_frames(tmp_path / "f.ndjson", lines)
    frames, code = _run(_argv(), env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file)})
    assert code == 0
    assert frames == [{"type": "never_seen_before", "x": 1}, {"type": "result"}]


def test_over_limit_line_is_discarded_with_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(claude_stream, "STREAM_LIMIT", 64 * KIB)
    lines = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "z" * (300 * KIB)}]}},
        {"type": "result"},
    ]
    frames_file = _write_frames(tmp_path / "f.ndjson", lines)
    with caplog.at_level(logging.WARNING, logger="cortex_command.claude_stream"):
        frames, code = _run(_argv(), env_extra={"FAKE_CLAUDE_FRAMES": str(frames_file)})
    assert code == 0
    assert frames == [{"type": "result"}]
    assert any("exceeded" in r.getMessage() for r in caplog.records)


def test_exception_in_body_terminates_child(tmp_path):
    frames_file = _write_frames(tmp_path / "f.ndjson", [{"type": "system"}])
    env = build_env({"FAKE_CLAUDE_FRAMES": str(frames_file), "FAKE_CLAUDE_SLEEP": "60"})
    holder = {}

    async def go():
        async with run_claude(_argv(), prompt="x", cwd=None, env=env) as run:
            holder["run"] = run
            async for _ in run.frames():
                raise KeyError("body failure")

    start = time.monotonic()
    with pytest.raises(KeyError):
        asyncio.run(go())
    assert time.monotonic() - start < 30
    assert holder["run"]._proc.returncode is not None


def test_nonexistent_cli_path_raises_spawn_error(tmp_path):
    missing = str(tmp_path / "no-such-claude")

    async def go():
        async with run_claude(build_argv(missing), prompt="x", cwd=None, env=build_env({})):
            pass

    with pytest.raises(ClaudeSpawnError) as info:
        asyncio.run(go())
    assert info.value.cli_path == missing
    assert isinstance(info.value.error, FileNotFoundError)
