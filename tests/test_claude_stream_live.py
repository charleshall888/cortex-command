"""Opt-in live test of the real ``claude`` CLI's frames (Task 19, spec R25).

Drives one real dispatch-shaped run through :func:`run_claude` against the
operator's actual ``claude`` binary and asserts the keys cortex reads off the
``assistant`` and ``result`` frames (see
``cortex/lifecycle/remove-claude-agent-sdk-dependency/live-verification.md``
for the frame shapes this pins).

Marked ``@pytest.mark.slow`` (opt-in via ``--run-slow``) because it makes one
real, billed model call (~$0.30). Run it exactly once per verification, not
in a loop. Skipped (not failed) when no ``claude`` CLI can be resolved, so it
degrades gracefully on an unauthenticated machine or in CI.

Uses ``asyncio.run()`` because pytest-asyncio is not a project dependency
(same convention as ``tests/test_claude_stream.py``).
"""

from __future__ import annotations

import asyncio

import pytest

from cortex_command.claude_stream import build_argv, build_env, run_claude
from cortex_command.cli_resolver import resolve_claude_cli


@pytest.mark.slow
def test_live_run_yields_assistant_and_result_frames_with_expected_keys():
    cli = resolve_claude_cli()
    if cli is None:
        pytest.skip("no claude CLI resolved on this machine")

    argv = build_argv(
        cli,
        max_turns=2,
        permission_mode="bypassPermissions",
        effort="low",
    )
    env = build_env({"CLAUDECODE": ""})

    async def go():
        frames = []
        async with run_claude(argv, prompt="Say OK.", cwd=None, env=env) as run:
            async for frame in run.frames():
                frames.append(frame)
        return frames, run.exit_code

    frames, exit_code = asyncio.run(go())

    assert exit_code == 0

    assistant_frames = [f for f in frames if f.get("type") == "assistant"]
    assert assistant_frames, "expected at least one assistant frame"
    assert any(
        isinstance(f.get("message", {}).get("content"), list)
        and isinstance(f.get("message", {}).get("model"), str)
        and f["message"]["model"]
        for f in assistant_frames
    ), "expected an assistant frame with a list message.content and a non-empty message.model"

    # Per live-verification.md (R7), frames can arrive after the result frame
    # (e.g. a trailing system/hook_response), so this only pins that there is
    # exactly one result frame — not that it is literally the last element.
    result_frames = [f for f in frames if f.get("type") == "result"]
    assert len(result_frames) == 1, f"expected exactly one result frame, got {len(result_frames)}"
    result = result_frames[0]
    for key in ("stop_reason", "num_turns", "total_cost_usd", "is_error"):
        assert key in result, f"result frame missing {key!r}: {result!r}"
