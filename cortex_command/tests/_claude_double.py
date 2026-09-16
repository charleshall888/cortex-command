"""Frame-level test double for :mod:`cortex_command.claude_stream`.

Replaces patching the SDK's query entry point (or the old ``_stubs.py`` SDK
stub) in unit tests. Callers build scripted stream-json frames with the
``*_frame`` helpers below, then hand them to :func:`fake_run_claude` to get a
callable shaped exactly like ``claude_stream.run_claude`` — same signature,
same ``async with ... as run: async for frame in run.frames(): ...`` usage,
same ``run.exit_code`` semantics — so production code written against the
real seam runs unchanged against this double.

Frames are plain ``dict``s matching the real ``claude`` stream-json shapes;
this module imports nothing from ``claude_stream`` and pulls in no SDK
package.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------


def assistant_frame(
    text: Optional[str] = None,
    *,
    model: str = "claude-test",
    tool_uses: Sequence[tuple[str, str, dict[str, Any]]] = (),
) -> dict[str, Any]:
    """Build an ``assistant`` frame with an optional text block and tool uses.

    ``tool_uses`` is a sequence of ``(id, name, input)`` tuples, one
    ``tool_use`` content block each, appended after the text block (if any).
    """
    content: list[dict[str, Any]] = []
    if text is not None:
        content.append({"type": "text", "text": text})
    for tool_id, name, tool_input in tool_uses:
        content.append(
            {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
        )
    return {"type": "assistant", "message": {"model": model, "content": content}}


def tool_result_frame(tool_use_id: str, is_error: bool = False) -> dict[str, Any]:
    """Build a ``user`` frame carrying a single ``tool_result`` content block."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                }
            ]
        },
    }


def result_frame(
    *,
    is_error: bool = False,
    subtype: str = "success",
    num_turns: int = 1,
    total_cost_usd: float = 0.01,
    stop_reason: Optional[str] = "end_turn",
    duration_ms: int = 10,
    terminal_reason: Optional[str] = None,
    api_error_status: Optional[int] = None,
    errors: Optional[list[Any]] = None,
    result: Optional[str] = None,
) -> dict[str, Any]:
    """Build a terminal ``result`` frame.

    All fields are always present (unset optionals carry ``None``) so a
    consumer can rely on the keys existing rather than probing with
    ``.get(..., default)``.
    """
    return {
        "type": "result",
        "is_error": is_error,
        "subtype": subtype,
        "num_turns": num_turns,
        "total_cost_usd": total_cost_usd,
        "stop_reason": stop_reason,
        "duration_ms": duration_ms,
        "terminal_reason": terminal_reason,
        "api_error_status": api_error_status,
        "errors": errors,
        "result": result,
    }


def system_frame(subtype: str = "init", **fields: Any) -> dict[str, Any]:
    """Build a ``system`` frame; ``fields`` are merged in alongside ``subtype``."""
    return {"type": "system", "subtype": subtype, **fields}


def rate_limit_frame(**fields: Any) -> dict[str, Any]:
    """Build a ``rate_limit_event`` frame.

    ``fields`` populate the nested ``rate_limit_info`` object — e.g.
    ``rate_limit_frame(status="allowed", rateLimitType="five_hour")`` — the
    same nesting a recorded session's stdout shows:
    ``{"type": "rate_limit_event", "rate_limit_info": {"status": ...,
    "resetsAt": ..., "rateLimitType": ...}, "uuid": ..., "session_id": ...}``.
    ``uuid``/``session_id`` are filled with fixed test placeholders since no
    observed consumer reads them.
    """
    return {
        "type": "rate_limit_event",
        "rate_limit_info": dict(fields),
        "uuid": "00000000-0000-0000-0000-000000000000",
        "session_id": "00000000-0000-0000-0000-000000000000",
    }


# ---------------------------------------------------------------------------
# Fake run_claude
# ---------------------------------------------------------------------------


class _FakeClaudeRun:
    """A scripted stand-in for ``claude_stream.ClaudeRun``.

    Mirrors the real class's usage shape: enter via ``async with``, drain
    frames via ``async for frame in run.frames()``, then read
    ``run.exit_code`` (``None`` until ``frames()`` has completed).
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        prompt: str,
        cwd: Optional[str],
        env: Mapping[str, str],
        on_stderr: Optional[Callable[[str], None]],
        frames: Sequence[dict[str, Any]],
        exit_code: int,
        stderr_lines: Sequence[str],
        spawn_error: Optional[Exception],
    ) -> None:
        self.argv = list(argv)
        self.prompt = prompt
        self.cwd = cwd
        self.env = env
        self.on_stderr = on_stderr
        self._frames = list(frames)
        self._exit_code_value = exit_code
        self._stderr_lines = list(stderr_lines)
        self._spawn_error = spawn_error
        self.exit_code: Optional[int] = None

    async def __aenter__(self) -> "_FakeClaudeRun":
        # The real ClaudeRun raises ClaudeSpawnError here, from the OSError
        # caught around asyncio.create_subprocess_exec in __aenter__ (not
        # from frames()) — a scripted spawn_error mirrors that same site.
        if self._spawn_error is not None:
            raise self._spawn_error
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def frames(self) -> AsyncIterator[dict[str, Any]]:
        for line in self._stderr_lines:
            if self.on_stderr is not None:
                self.on_stderr(line)
        for frame in self._frames:
            yield frame
        self.exit_code = self._exit_code_value


def fake_run_claude(
    frames: Sequence[dict[str, Any]],
    *,
    exit_code: int = 0,
    stderr_lines: Sequence[str] = (),
    spawn_error: Optional[Exception] = None,
    capture: Optional[dict[str, Any]] = None,
) -> Callable[..., _FakeClaudeRun]:
    """Return a callable shaped like ``claude_stream.run_claude``.

    The returned callable records its ``argv``/``prompt``/``cwd``/``env``
    into ``capture`` (when given) and returns a :class:`_FakeClaudeRun` that
    yields ``frames``, feeds ``stderr_lines`` to ``on_stderr``, and sets
    ``exit_code`` once ``frames()`` completes. If ``spawn_error`` is given,
    entering the returned run's ``async with`` block raises it instead.
    """

    def _run_claude(
        argv: Sequence[str],
        *,
        prompt: str,
        cwd: Optional[str],
        env: Mapping[str, str],
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> _FakeClaudeRun:
        if capture is not None:
            capture["argv"] = list(argv)
            capture["prompt"] = prompt
            capture["cwd"] = cwd
            capture["env"] = env
        return _FakeClaudeRun(
            argv,
            prompt=prompt,
            cwd=cwd,
            env=env,
            on_stderr=on_stderr,
            frames=frames,
            exit_code=exit_code,
            stderr_lines=stderr_lines,
            spawn_error=spawn_error,
        )

    return _run_claude
