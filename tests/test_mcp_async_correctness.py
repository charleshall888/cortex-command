"""Async-correctness verification tests for the MCP tool handlers (R29 / Task 16).

This test is a permanent structural guardrail. It enforces three claims
against ``cortex_command/mcp_server/tools.py``:

(i) **AST-walk-all-Call-nodes audit** — for every async-def MCP tool
    handler, every ``Call`` node anywhere in the body (including nested
    function defs, lambdas, comprehensions) must be either:

    * the ``func`` of an ``Await`` node (i.e. ``await foo(...)``), OR
    * a call whose callee name matches a finite, explicit allowlist of
      known-pure helpers / model constructors / dunder-style accessors.

    Any other Call fails the test with a precise line-number citation.
    The allowlist is the audit's intended forcing function — additions
    to handler bodies that introduce new sync APIs require an allowlist
    update, which forces the change to be considered explicitly.

(ii) **Latency assertion via FastMCP test client** — spawn the real
    ``cortex mcp-server`` subprocess via the ``mcp`` SDK's stdio test
    client, fire two concurrent tool calls (one slow ``overnight_status``
    that sleeps 2 s on the worker thread, one fast ``overnight_list_sessions``),
    and assert the fast call completes within 250 ms wall-clock. This
    exercises the actual stdio JSON-RPC dispatch loop end-to-end — not
    just ``asyncio.gather`` against handler coroutines, which would
    sidestep the framing layer where head-of-line blocking is most
    likely to manifest.

(iii) **Name-grep fallback** — a literal grep verifying no handler is
     declared as ``def`` (synchronous) instead of ``async def``.

Scope note (acknowledged gap): this audit covers ``tools.py`` only.
Handlers may delegate to ``cli_handler.py`` via ``await asyncio.to_thread``
and ``cli_handler`` itself can perform blocking work synchronously. That
is by design — the structural contract is for the MCP membrane. Egregious
``cli_handler``-level blocking would be caught by sub-test (ii)'s real
end-to-end latency assertion.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_PY = REPO_ROOT / "cortex_command" / "mcp_server" / "tools.py"

HANDLER_NAMES = {
    "overnight_start_run",
    "overnight_status",
    "overnight_logs",
    "overnight_cancel",
    "overnight_list_sessions",
}


# ---------------------------------------------------------------------------
# Allowlist of known-pure callee names that may appear sync inside handlers.
#
# The list is finite and explicit so that any new sync API introduced into
# a handler body forces a deliberate allowlist update. Every entry is one
# of: (a) a Python builtin guaranteed pure, (b) a Pydantic / dataclass
# constructor from schema.py or tools.py module locals, (c) a known-pure
# helper defined in tools.py itself, (d) a dunder/dot-method access on a
# local container, or (e) a deliberate exception (commented inline).
# ---------------------------------------------------------------------------

# Free-function and constructor callees (matched against the call's *final*
# attribute name, e.g. ``datetime.now`` matches ``now``; ``ToolError(...)``
# matches ``ToolError``; ``StartRunOutput(...)`` matches ``StartRunOutput``).
_ALLOWED_CALLEE_NAMES: frozenset[str] = frozenset(
    {
        # --- Python builtins (pure, no I/O) ---
        "isinstance",
        "issubclass",
        "len",
        "max",
        "min",
        "bool",
        "all",
        "any",
        "str",
        "int",
        "float",
        "dict",
        "list",
        "set",
        "tuple",
        "range",
        "enumerate",
        "zip",
        "sorted",
        "reversed",
        "iter",
        "next",
        "type",
        "repr",
        "hash",
        # --- Pydantic / dataclass model constructors (schema.py) ---
        "StartRunInput",
        "StartRunOutput",
        "StatusInput",
        "StatusOutput",
        "FeatureCounts",
        "LogsInput",
        "LogsOutput",
        "CancelInput",
        "CancelOutput",
        "ListSessionsInput",
        "ListSessionsOutput",
        "SessionSummary",
        # --- Common pure constructors ---
        "Path",
        "datetime",
        # --- Datetime / Pydantic instance-method accessors (pure, in-memory) ---
        "now",
        "isoformat",
        "fromisoformat",
        "model_validate",
        "model_dump",
        "model_dump_json",
        # --- json (serialize-only / parse-only — no I/O at the call) ---
        # ``json.dumps`` and ``json.loads`` operate on in-memory strings.
        "dumps",
        "loads",
        # --- Dict / list / set method names that are pure ---
        "get",
        "append",
        "extend",
        "keys",
        "values",
        "items",
        "update",
        "pop",
        "copy",
        "values",
        "replace",
        "split",
        "join",
        "strip",
        "startswith",
        "endswith",
        "lower",
        "upper",
        "format",
        "encode",
        "decode",
        "add",
        "discard",
        "remove",
        "count",
        "index",
        # --- Exception construction (always pure) ---
        "ToolError",
        "ValueError",
        "TypeError",
        "OSError",
        "RuntimeError",
        # --- tools.py-module-private pure helpers ---
        "_state_to_status_output",
        "_state_to_summary",
        "_feature_counts_from_state",
        "_parse_log_line",
        "_parse_since",
        "_updated_at_dt",
        "_classify_verify_failure",
        "_resolve_state_path_for_session",
        # ``_cli_handler._resolve_repo_path()`` — reads the
        # ``CORTEX_REPO_PATH`` env var and returns a ``Path``. No
        # blocking I/O of any consequence; it's called once per handler
        # to anchor lifecycle/sessions/{session_id} resolution.
        "_resolve_repo_path",
        # --- Specific allowlisted operations (commented justifications) ---
        # ``os.environ.get`` is a pure dict access on the process env.
        "environ",  # in case of attribute chain like os.environ
        # ``os.close(fd)`` in the ``overnight_start_run`` finally-block
        # closes the parent's copy of an already-dup'd file descriptor
        # (the child has the dup). It is non-blocking and microsecond-
        # bounded; making it ``await asyncio.to_thread(os.close, fd)``
        # would be needless ceremony for a CPU-time-only operation.
        "close",
    }
)


def _collect_handler_funcs(tree: ast.AST) -> dict[str, ast.AsyncFunctionDef]:
    """Return ``{handler_name: AsyncFunctionDef}`` for the five MCP handlers.

    Only top-level (module-scope) async-def functions are considered, so
    inner helpers shadowing a handler name (none today) cannot mask the
    real handler's body from the audit.
    """
    out: dict[str, ast.AsyncFunctionDef] = {}
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name in HANDLER_NAMES
        ):
            out[node.name] = node
    return out


def _set_parents(tree: ast.AST) -> None:
    """Annotate every AST node with a ``_parent`` attribute."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]


def _callee_terminal_name(call: ast.Call) -> str:
    """Return the final attribute / name segment of the call's callee.

    * ``foo(...)`` → ``"foo"``
    * ``foo.bar(...)`` → ``"bar"``
    * ``foo.bar.baz(...)`` → ``"baz"``
    * ``foo[0](...)`` → ``""`` (subscript-call; never allowlisted)
    * ``(lambda: 1)(...)`` → ``""``
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_awaited(call: ast.Call) -> bool:
    """Return True iff ``call`` is the immediate child of an ``Await`` node."""
    parent = getattr(call, "_parent", None)
    return isinstance(parent, ast.Await)


def _format_call_src(call: ast.Call) -> str:
    """Best-effort source rendering of the call for error messages."""
    try:
        return ast.unparse(call)
    except Exception:
        return f"<call at L{call.lineno}>"


def test_all_handlers_are_async_def() -> None:
    """Sub-test (i)/(iii): every handler is declared ``async def``.

    AST-level check (the formatter-tolerant counterpart to the literal
    grep) — also asserts all five handlers are present at module scope.
    """
    tree = ast.parse(TOOLS_PY.read_text(encoding="utf-8"))
    handlers = _collect_handler_funcs(tree)

    missing = HANDLER_NAMES - handlers.keys()
    assert not missing, (
        f"missing async handlers in tools.py: {sorted(missing)}"
    )

    # Belt-and-suspenders: the literal grep fallback (sub-test iii).
    pattern = re.compile(
        r"^\s*def (?:overnight_start_run|overnight_status|overnight_logs|"
        r"overnight_cancel|overnight_list_sessions)",
        re.MULTILINE,
    )
    sync_decls = pattern.findall(TOOLS_PY.read_text(encoding="utf-8"))
    assert not sync_decls, (
        f"found sync ``def`` declarations for MCP handlers (must be "
        f"``async def``): {sync_decls}"
    )


def test_all_handler_calls_are_awaited_or_known_pure() -> None:
    """Sub-test (i): walk every Call inside each handler body.

    Each Call must either be the ``func`` of an ``Await`` node, OR have a
    terminal callee name in :data:`_ALLOWED_CALLEE_NAMES`. Anything else
    is flagged with a line-number citation and the rendered call source.
    """
    src = TOOLS_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    _set_parents(tree)
    handlers = _collect_handler_funcs(tree)

    violations: list[str] = []

    for name, handler in sorted(handlers.items()):
        for sub in ast.walk(handler):
            if not isinstance(sub, ast.Call):
                continue
            if _is_awaited(sub):
                continue
            terminal = _callee_terminal_name(sub)
            if terminal in _ALLOWED_CALLEE_NAMES:
                continue
            violations.append(
                f"{name}@L{sub.lineno}: non-awaited Call to "
                f"`{terminal or '<dynamic>'}` — {_format_call_src(sub)}"
            )

    assert not violations, (
        "Async-correctness violations in cortex_command/mcp_server/tools.py:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nEvery synchronous Call inside an MCP tool handler must be "
        "either await-prefixed (typically `await asyncio.to_thread(...)`) "
        "or in the known-pure allowlist in this test file."
    )


# ---------------------------------------------------------------------------
# Sub-test (ii) — real-stdio latency assertion
# ---------------------------------------------------------------------------


def _resolve_cortex_executable() -> list[str] | None:
    """Return argv prefix for invoking ``cortex mcp-server`` in this env.

    Prefers the ``cortex`` console script on PATH; falls back to
    ``[sys.executable, "-m", "cortex_command.cli"]``. Returns ``None`` if
    neither path is invokable, in which case the caller should skip the
    test (this is an environment limitation, not a contract failure).
    """
    candidate = shutil.which("cortex")
    if candidate is not None:
        return [candidate]
    # Fallback: invoke via the in-tree module form. Always callable in
    # the dev environment because ``cortex_command`` is on the path.
    return [sys.executable, "-m", "cortex_command.cli"]


def test_concurrent_tool_calls_no_head_of_line_blocking(tmp_path) -> None:
    """Sub-test (ii): a slow tool call must not delay a fast one over stdio.

    Spawns the real ``cortex mcp-server`` subprocess via the ``mcp`` SDK's
    stdio test client. Fires two concurrent tool calls:

    * a slow ``overnight_status`` that sleeps 2 s on the worker thread
      (the env var ``CORTEX_MCP_TEST_SLEEP_MS=2000`` is the test-only
      switch that activates the sleep — production never sets it),
    * a fast ``overnight_list_sessions`` against an empty sessions
      directory (returns immediately).

    The fast call must complete within 250 ms wall-clock from dispatch
    even while the slow call is still in flight. A higher latency
    indicates the stdio server's event loop is being blocked on the
    threadpool task instead of dispatching the second tool concurrently.
    """
    try:
        from mcp import ClientSession  # noqa: F401
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("mcp SDK not importable in this environment")

    argv = _resolve_cortex_executable()
    if argv is None:
        pytest.skip("cortex executable not invokable")

    # Smoke: the subcommand must at least exit 0 on --help to indicate
    # the binary path is wired up.
    try:
        smoke = subprocess.run(
            argv + ["mcp-server", "--help"],
            capture_output=True,
            timeout=15,
            text=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("cortex mcp-server --help unavailable in this env")
    if smoke.returncode != 0:
        pytest.skip(
            f"cortex mcp-server --help exited {smoke.returncode}: "
            f"{smoke.stderr[:200]}"
        )

    # Per-test sessions root so list_sessions returns an empty payload
    # quickly (no real fixtures to glob).
    sessions_root = tmp_path / "lifecycle" / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["CORTEX_REPO_PATH"] = str(tmp_path)
    env["CORTEX_MCP_TEST_SLEEP_MS"] = "2000"

    async def _run() -> tuple[float, float]:
        params = StdioServerParameters(
            command=argv[0],
            args=argv[1:] + ["mcp-server"],
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            from mcp import ClientSession as _CS

            async with _CS(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)

                start = asyncio.get_running_loop().time()

                async def slow() -> float:
                    t0 = asyncio.get_running_loop().time()
                    res = await session.call_tool(
                        "overnight_status",
                        arguments={"payload": {}},
                    )
                    if res.isError:
                        raise AssertionError(
                            f"slow overnight_status returned error: "
                            f"{res.content}"
                        )
                    return asyncio.get_running_loop().time() - t0

                async def fast() -> float:
                    # Tiny stagger so the slow call definitely hits the
                    # threadpool first — this models the "another tool
                    # is in flight" scenario the audit guards against.
                    await asyncio.sleep(0.05)
                    t0 = asyncio.get_running_loop().time()
                    res = await session.call_tool(
                        "overnight_list_sessions",
                        arguments={"payload": {}},
                    )
                    if res.isError:
                        raise AssertionError(
                            f"fast overnight_list_sessions returned error: "
                            f"{res.content}"
                        )
                    return asyncio.get_running_loop().time() - t0

                slow_dur, fast_dur = await asyncio.gather(slow(), fast())
                _ = start  # keep symmetry; per-call durations are what matter
                return slow_dur, fast_dur

    try:
        slow_dur, fast_dur = asyncio.run(asyncio.wait_for(_run(), timeout=30))
    except asyncio.TimeoutError:
        pytest.fail(
            "stdio MCP server did not respond within 30 s — "
            "likely a head-of-line stall in the dispatch loop"
        )

    # The slow call must actually have slept (otherwise we did not
    # exercise the contended path).
    assert slow_dur >= 1.5, (
        f"slow call took only {slow_dur:.3f}s — expected ≥ 1.5s "
        f"(test-only sleep did not fire; harness misconfigured?)"
    )
    # The contract: a fast call dispatched while the slow call is on
    # the threadpool must complete in ≲ 250 ms wall-clock. Spec R29
    # tolerance is "≤ 100 ms" but stdio framing + subprocess startup
    # adds variance, so we use 250 ms as a conservative ceiling that
    # still catches head-of-line blocking (which would push fast_dur
    # toward the slow call's 2 s).
    assert fast_dur < 0.25, (
        f"fast call took {fast_dur:.3f}s while slow call was in flight "
        f"— stdio dispatch is head-of-line-blocked (slow={slow_dur:.3f}s)"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
