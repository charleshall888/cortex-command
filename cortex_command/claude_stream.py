"""Spawn the operator's ``claude`` CLI and yield its stream-json frames.

This is the one seam between cortex and a headless ``claude`` run: it builds
the argv (``-p --output-format stream-json --verbose``, prompt on stdin) and
the child environment, spawns the process, writes the prompt, drains stderr
concurrently, and yields one parsed ``dict`` per stream-json line. It does not
interpret frame types — callers (``pipeline/dispatch.py``, ``discovery.py``)
own classification.

Stream rules:

- stdout is read with a line limit of :data:`STREAM_LIMIT` (the asyncio 64 KiB
  default truncates real ``assistant`` frames); a line over the limit is
  discarded with a warning, never raised.
- A blank line, non-JSON line, non-object, or object without a string
  ``type`` is skipped silently; every other object is yielded unchanged.
- The process ends the run, not any frame: stdout is read to EOF, then the
  child is awaited and :attr:`ClaudeRun.exit_code` is set.
- On an exception, cancellation, or early exit from the ``async with`` body
  while the child is alive, the child is terminated, given 5 s, then killed.

Leaf module: stdlib-only. It must not import the ``pipeline`` /
``overnight`` / ``discovery`` — those depend on it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Per-line read limit for the child's stdout and stderr (bytes).
STREAM_LIMIT = 16 * 1024 * 1024

#: Seconds to wait after SIGTERM before SIGKILL during cleanup.
TERMINATE_GRACE_S = 5.0


class ClaudeSpawnError(Exception):
    """The ``claude`` child could not be started.

    ``cli_path`` is the executable that was tried; ``error`` is the underlying
    ``OSError`` (also chained as ``__cause__``).
    """

    def __init__(self, cli_path: str, error: OSError) -> None:
        super().__init__(f"could not start claude at {cli_path!r}: {error}")
        self.cli_path = cli_path
        self.error = error


def build_env(overlay: Mapping[str, str]) -> dict[str, str]:
    """Return the child environment: parent env minus ``CLAUDECODE``, plus overlay.

    An overlay value of ``""`` for ``CLAUDECODE`` leaves the key absent, so a
    caller clearing the nested-session guard never exports an empty variable.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.update(overlay)
    if env.get("CLAUDECODE") == "":
        del env["CLAUDECODE"]
    return env


def build_argv(
    cli_path: str,
    *,
    max_turns: Optional[int] = None,
    max_budget_usd: Optional[float] = None,
    permission_mode: Optional[str] = None,
    allowed_tools: Optional[Sequence[str]] = None,
    system_prompt: Optional[str] = None,
    settings: Optional[str] = None,
    effort: Optional[str] = None,
) -> list[str]:
    """Build the ``claude`` argv. The prompt is never positional — it goes on stdin."""
    argv = [cli_path, "-p", "--output-format", "stream-json", "--verbose"]
    if max_turns is not None:
        argv += ["--max-turns", str(max_turns)]
    if max_budget_usd is not None:
        argv += ["--max-budget-usd", str(max_budget_usd)]
    if permission_mode is not None:
        argv += ["--permission-mode", permission_mode]
    if allowed_tools is not None:
        argv += ["--allowedTools", ",".join(allowed_tools)]
    if system_prompt is not None:
        argv += ["--system-prompt", system_prompt]
    if settings is not None:
        argv += ["--settings", settings]
    if effort is not None:
        argv += ["--effort", effort]
    return argv


async def _read_line(reader: asyncio.StreamReader) -> tuple[Optional[bytes], bool]:
    """Read one newline-terminated line.

    Returns ``(line, overlong)``: ``line`` is ``None`` at EOF; ``overlong`` is
    True when a line exceeded the reader limit and was discarded (``line`` is
    then ``b""``).
    """
    try:
        return await reader.readuntil(b"\n"), False
    except asyncio.IncompleteReadError as exc:
        return (exc.partial or None), False
    except asyncio.LimitOverrunError as exc:
        consumed = exc.consumed
    # Discard the over-limit line through its terminating newline (or EOF).
    while True:
        try:
            await reader.readexactly(consumed)
        except asyncio.IncompleteReadError:
            return b"", True
        try:
            await reader.readuntil(b"\n")
            return b"", True
        except asyncio.IncompleteReadError:
            return b"", True
        except asyncio.LimitOverrunError as exc:
            consumed = exc.consumed


def _parse_frame(line: bytes) -> Optional[dict[str, Any]]:
    text = line.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
        return None
    return obj


class ClaudeRun:
    """One ``claude`` child process; use via ``async with run_claude(...) as run``."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        prompt: str,
        cwd: Optional[str],
        env: dict[str, str],
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.argv = list(argv)
        self.prompt = prompt
        self.cwd = cwd
        self.env = env
        self.on_stderr = on_stderr
        self.exit_code: Optional[int] = None
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stdin_task: Optional[asyncio.Task[None]] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> "ClaudeRun":
        cli_path = self.argv[0] if self.argv else ""
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=self.env,
                limit=STREAM_LIMIT,
            )
        except OSError as exc:
            raise ClaudeSpawnError(cli_path, exc) from exc
        self._stdin_task = asyncio.create_task(self._write_prompt())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        proc = self._proc
        try:
            if proc is not None and proc.returncode is None:
                await self._terminate(proc)
        finally:
            tasks = [t for t in (self._stdin_task, self._stderr_task) if t is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            # return_exceptions: a helper's error or cancellation must not mask
            # the body's exception.
            await asyncio.gather(*tasks, return_exceptions=True)

    async def frames(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed frames until stdout EOF, then await exit and set ``exit_code``."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise RuntimeError("ClaudeRun.frames() called outside `async with`")
        while True:
            line, overlong = await _read_line(proc.stdout)
            if line is None:
                break
            if overlong:
                logger.warning(
                    "claude stdout line exceeded %d bytes; discarded", STREAM_LIMIT
                )
                continue
            frame = _parse_frame(line)
            if frame is not None:
                yield frame
        self.exit_code = await proc.wait()
        for task in (self._stdin_task, self._stderr_task):
            if task is not None:
                await task

    async def _write_prompt(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        stdin = proc.stdin
        try:
            stdin.write(self.prompt.encode("utf-8"))
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                stdin.close()
                await stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _drain_stderr(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stderr is not None
        while True:
            line, overlong = await _read_line(proc.stderr)
            if line is None:
                return
            if overlong or self.on_stderr is None:
                continue
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            try:
                self.on_stderr(text)
            except Exception:  # noqa: BLE001 — a callback bug must not stall the drain
                logger.debug("on_stderr callback raised; ignored", exc_info=True)

    async def _terminate(self, proc: asyncio.subprocess.Process) -> None:
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_S)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            await proc.wait()


def run_claude(
    argv: Sequence[str],
    *,
    prompt: str,
    cwd: Optional[str],
    env: dict[str, str],
    on_stderr: Optional[Callable[[str], None]] = None,
) -> ClaudeRun:
    """Return a :class:`ClaudeRun` async context manager for ``argv``."""
    return ClaudeRun(argv, prompt=prompt, cwd=cwd, env=env, on_stderr=on_stderr)
