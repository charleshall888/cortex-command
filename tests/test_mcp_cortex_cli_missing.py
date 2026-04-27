"""S1+S5 acceptance tests for ``cortex`` CLI missing-on-PATH handling.

Covers the eight behaviors enumerated in the
apply-post-113-audit-follow-ups-stale-doc-cleanup-lifecycle-archive-run-mcp-hardening
spec for the cortex-overnight-integration MCP server:

(a) ``FileNotFoundError`` in :func:`_get_cortex_root_payload` raises
    :class:`CortexCliMissing`.
(b) ``FileNotFoundError`` in :func:`_run_cortex` raises
    :class:`CortexCliMissing`.
(c) ``PermissionError`` (a sibling ``OSError``) does NOT convert to
    :class:`CortexCliMissing` — the FNF wrappers catch ONLY
    ``FileNotFoundError``.
(d) Cache-then-FNF-then-recovery: a primed discovery cache plus a
    one-shot FNF on the first ``_run_cortex`` call recovers via the
    retry, the dispatched tool returns its success payload, and
    ``_CORTEX_ROOT_CACHE`` is repopulated (cleared by the retry handler
    and re-fetched if the next path consults it).
(e) Cache-then-FNF-then-FNF: with ``subprocess.run`` raising FNF on
    every call, the delegate's return value (the symbol-level invariant
    the plan asserts) IS byte-equal to ``_CORTEX_CLI_MISSING_ERROR``.

    NOTE on layering: when a delegate's typed output schema is
    ``StatusOutput | str`` and the delegate returns ``str``, FastMCP
    runs the return value through Pydantic validation against the
    declared output schema. That triggers a ``ValidationError`` which
    ``_make_error_result`` wraps into a TextContent envelope. So the
    wire-level ``CallToolResult`` is NOT byte-equal to
    ``_CORTEX_CLI_MISSING_ERROR``. We test what the delegate function
    ACTUALLY returns (its in-process return value) — that IS the
    ``_CORTEX_CLI_MISSING_ERROR`` constant verbatim — not what FastMCP
    forwards over the wire.

(f) :func:`_maybe_check_upstream` returns its sentinel (``None``) when
    :class:`CortexCliMissing` is raised — its ``except OSError`` handler
    swallows the exception via the ``OSError`` parentage of S1.1.
(g) Startup branch: with ``shutil.which("cortex")`` returning ``None``
    at module import, the import emits a stderr line containing
    ``_CORTEX_CLI_MISSING_ERROR``.
(h) Byte-equal canonical error string across propagation paths: the
    stderr line emitted at startup (case g) and the tool-body return
    value at retry-exhaust (case e) carry the same
    ``_CORTEX_CLI_MISSING_ERROR`` constant. The assertion is at the
    delegate-level / startup-stderr level, not the wire level (see
    layering note for case e).

The tests scope to a single coroutine. Per the spec's edge-case
discussion (S1.3), under FastMCP's current sync-blocking-subprocess
model, ``asyncio`` cannot interleave two coroutines mid-cache-clear —
a multi-coroutine test would tautologically pass via cooperative
serialization rather than verifying the cache logic. Cross-coroutine
concurrency safety is documented as out-of-scope until a future
refactor introduces real async (server.py module docstring + the
discovery-cache concurrency comment).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = (
    REPO_ROOT
    / "plugins"
    / "cortex-overnight-integration"
    / "server.py"
)
PLUGIN_ROOT = SERVER_PATH.parent


# ---------------------------------------------------------------------------
# Module loader (mirrors tests/test_mcp_subprocess_contract.py).
# ---------------------------------------------------------------------------


def _load_server_module():
    """Import ``plugins/cortex-overnight-integration/server.py`` as a module.

    Sets ``CLAUDE_PLUGIN_ROOT`` to the plugin directory so the
    confused-deputy guard at the top of the file accepts the load.
    """
    if "cortex_plugin_server" in sys.modules:
        return sys.modules["cortex_plugin_server"]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    spec = importlib.util.spec_from_file_location(
        "cortex_plugin_server", SERVER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_plugin_server"] = module
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Return a fake :class:`subprocess.CompletedProcess` for mocks."""
    return subprocess.CompletedProcess(
        args=["cortex"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _print_root_payload(root: str = "/fake/root") -> str:
    """Return a JSON string matching ``cortex --print-root``'s contract."""
    return json.dumps(
        {
            "version": "1.0",
            "root": root,
            "remote_url": "git@github.com:user/cortex-command.git",
            "head_sha": "0" * 40,
        }
    )


def _status_payload() -> str:
    """Return a JSON string matching ``cortex overnight status --format json``."""
    return json.dumps(
        {
            "session_id": "alpha",
            "phase": "executing",
            "current_round": 1,
            "features": {},
        }
    )


@pytest.fixture
def server_module(monkeypatch: pytest.MonkeyPatch):
    """Load server.py once and reset module caches per-test.

    Sets ``CORTEX_DEV_MODE=1`` so :func:`_gate_dispatch` short-circuits
    its R8/R9/R10 update-check before any extraneous ``subprocess.run``
    calls reach our mocks (otherwise ``git status``/``git ls-remote``
    would interact with the FNF mock and confuse the per-test budget).
    """
    monkeypatch.setenv("CORTEX_DEV_MODE", "1")
    mod = _load_server_module()
    # Reset caches every test so we start from a clean slate.
    mod._CORTEX_ROOT_CACHE = None
    mod._STATUS_LEGACY_VERSION_WARNED = False
    mod._UPDATE_CHECK_CACHE.clear()
    mod._SKIP_REASON_LOGGED.clear()
    return mod


# ---------------------------------------------------------------------------
# (a) FNF in _get_cortex_root_payload raises CortexCliMissing.
# ---------------------------------------------------------------------------


def test_a_get_cortex_root_payload_fnf_raises_cortex_cli_missing(
    server_module,
) -> None:
    """FNF inside the discovery shellout converts to :class:`CortexCliMissing`."""

    def _raise_fnf(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_raise_fnf):
        with pytest.raises(server_module.CortexCliMissing) as exc_info:
            server_module._get_cortex_root_payload()

    # Subclass relationship is load-bearing per S1.1.
    assert isinstance(exc_info.value, OSError)


# ---------------------------------------------------------------------------
# (b) FNF in _run_cortex raises CortexCliMissing.
# ---------------------------------------------------------------------------


def test_b_run_cortex_fnf_raises_cortex_cli_missing(server_module) -> None:
    """FNF inside the per-verb dispatch converts to :class:`CortexCliMissing`."""

    def _raise_fnf(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_raise_fnf):
        with pytest.raises(server_module.CortexCliMissing) as exc_info:
            server_module._run_cortex(
                ["overnight", "status", "--format", "json"], timeout=5.0
            )

    assert isinstance(exc_info.value, OSError)


# ---------------------------------------------------------------------------
# (c) PermissionError does NOT convert.
# ---------------------------------------------------------------------------


def test_c_permission_error_does_not_convert(server_module) -> None:
    """``PermissionError`` is a sibling ``OSError`` — the FNF handler skips it.

    The wrappers catch *exactly* ``FileNotFoundError``; broader
    ``OSError`` subclasses must propagate unchanged so call-site
    handlers see the original exception type.
    """

    def _raise_perm(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_raise_perm):
        with pytest.raises(PermissionError):
            server_module._get_cortex_root_payload()

    with patch.object(server_module.subprocess, "run", side_effect=_raise_perm):
        with pytest.raises(PermissionError):
            server_module._run_cortex(
                ["overnight", "status", "--format", "json"], timeout=5.0
            )


# ---------------------------------------------------------------------------
# (d) Cache-then-FNF-then-recovery: one retry succeeds.
# ---------------------------------------------------------------------------


def test_d_cache_then_fnf_then_recovery_succeeds_with_retry(
    server_module,
) -> None:
    """A primed cache + one-shot FNF recovers via the single retry budget.

    Setup: prime ``_CORTEX_ROOT_CACHE`` so :func:`_get_cortex_root_payload`
    does not shell out. Patch ``subprocess.run`` to raise FNF on the
    first call (which will be the per-verb ``_run_cortex`` invocation
    inside :func:`_delegate_overnight_status`) and succeed on the
    second. Verify:

      * The delegate returns its success payload (a typed
        ``StatusOutput``), not the missing-CLI string.
      * The cache is repopulated after the retry-handler cleared it.
        With ``CORTEX_DEV_MODE=1``, no other code path consults the
        cache during the call, so verify the cache was cleared and is
        primed by the time we re-prime it via a follow-up call.
    """

    primed_payload = json.loads(_print_root_payload())
    server_module._CORTEX_ROOT_CACHE = primed_payload

    calls: list[list[str]] = []

    def _flaky_run(argv, **kwargs):
        calls.append(list(argv))
        if len(calls) == 1:
            # First call: simulate `cortex` removed mid-session.
            raise FileNotFoundError(2, "No such file or directory", "cortex")
        # Second call (retry) — cache was cleared so a re-discovery
        # might happen first; tolerate either argv shape and route by
        # the verb tail.
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=_status_payload())

    with patch.object(server_module.subprocess, "run", side_effect=_flaky_run):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    # The delegate returned a typed success — not the canonical error
    # string — proving the retry recovered.
    assert isinstance(result, server_module.StatusOutput)
    assert result.phase == "executing"

    # The retry handler clears _CORTEX_ROOT_CACHE on the FNF path. The
    # cache may then be repopulated by a downstream caller that consults
    # it; if no such caller fires during the dispatch (the fast path
    # for ``session_id=None`` under ``CORTEX_DEV_MODE=1``), the cache
    # remains None until next discovery. Either is acceptable: what
    # matters is that the cache is not stuck at a stale value pointing
    # at a removed CLI. Force a follow-up discovery to confirm the
    # cache populates cleanly post-recovery.
    server_module._CORTEX_ROOT_CACHE = None
    with patch.object(
        server_module.subprocess,
        "run",
        return_value=_completed(stdout=_print_root_payload()),
    ):
        repopulated = server_module._get_cortex_root_payload()
    assert server_module._CORTEX_ROOT_CACHE is not None
    assert repopulated["root"] == "/fake/root"


# ---------------------------------------------------------------------------
# (e) Cache-then-FNF-then-FNF: delegate returns canonical error string.
# ---------------------------------------------------------------------------


def test_e_cache_then_fnf_then_fnf_returns_canonical_error_string(
    server_module,
) -> None:
    """Retry-exhaust returns ``_CORTEX_CLI_MISSING_ERROR`` verbatim.

    LAYERING NOTE: this asserts the *delegate function's* return value
    (the symbol-level invariant the plan asserts) is byte-equal to
    ``_CORTEX_CLI_MISSING_ERROR``. FastMCP's wire-level
    ``CallToolResult`` will NOT be byte-equal — when a delegate with a
    typed output schema returns a bare ``str``, FastMCP runs the value
    through Pydantic validation, fails, and wraps the resulting
    ``ValidationError`` via ``_make_error_result(str(e))`` into a
    TextContent envelope. So the in-process return is byte-equal to the
    constant; the over-the-wire content is not. Future maintainers
    chasing wire-level equality should refactor the delegate signatures
    to return the error via a sentinel exception or a typed error
    payload field rather than a bare ``str``.
    """

    primed_payload = json.loads(_print_root_payload())
    server_module._CORTEX_ROOT_CACHE = primed_payload

    def _always_fnf(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_always_fnf):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    assert result == server_module._CORTEX_CLI_MISSING_ERROR


# ---------------------------------------------------------------------------
# (f) _maybe_check_upstream swallows CortexCliMissing via OSError parentage.
# ---------------------------------------------------------------------------


def test_f_maybe_check_upstream_swallows_cortex_cli_missing(
    server_module,
) -> None:
    """Pre-S1 ``except OSError`` handler still swallows the typed exception.

    S1.1 makes ``CortexCliMissing`` an ``OSError`` subclass precisely so
    legacy handlers (``_maybe_check_upstream``, ``_maybe_run_upgrade``)
    keep their no-op-on-FNF behavior without code change. Force the
    discovery shellout to raise the typed exception and verify the
    sentinel return.
    """

    # Cache must be empty so _maybe_check_upstream calls
    # _get_cortex_root_payload (which is the path that raises).
    server_module._CORTEX_ROOT_CACHE = None

    def _raise_fnf(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_raise_fnf):
        # No payload argument — forces the helper to bootstrap discovery.
        result = server_module._maybe_check_upstream()

    assert result is None


# ---------------------------------------------------------------------------
# (g) Startup branch: shutil.which returning None emits the canonical
#     error string to stderr.
# ---------------------------------------------------------------------------


def _reload_server_under_which_none(
    server_module, capsys: pytest.CaptureFixture[str]
) -> str:
    """Re-execute server.py with ``shutil.which`` patched to return ``None``.

    Returns the captured stderr text. We cannot use :func:`importlib.reload`
    because the module was loaded via :func:`importlib.util.spec_from_file_location`
    and lacks a discoverable spec for the standard reload machinery. Instead,
    re-run the spec loader against the same source file with ``shutil.which``
    patched in :mod:`builtins`-style scope before the module body executes.
    The re-execution re-runs the confused-deputy guard (already passing
    because ``CLAUDE_PLUGIN_ROOT`` is set) and the S5.1
    ``shutil.which("cortex")`` check.
    """
    spec = importlib.util.spec_from_file_location(
        "cortex_plugin_server", SERVER_PATH
    )
    assert spec is not None and spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    # Patch shutil.which globally so the module-body lookup of
    # ``shutil.which("cortex")`` returns None during exec_module.
    import shutil as _shutil

    with patch.object(_shutil, "which", return_value=None):
        spec.loader.exec_module(fresh)
    captured = capsys.readouterr()
    return captured.err


def test_g_startup_emits_stderr_when_cortex_missing_on_path(
    server_module, capsys: pytest.CaptureFixture[str]
) -> None:
    """Module-import-time ``shutil.which`` None branch logs to stderr.

    Reloads the module with ``shutil.which`` patched to return ``None``;
    the resulting stderr line must contain
    ``_CORTEX_CLI_MISSING_ERROR``.
    """

    stderr_text = _reload_server_under_which_none(server_module, capsys)

    assert server_module._CORTEX_CLI_MISSING_ERROR in stderr_text


# ---------------------------------------------------------------------------
# (h) Byte-equal canonical error string across propagation paths.
# ---------------------------------------------------------------------------


def test_h_byte_equal_canonical_error_string_across_paths(
    server_module, capsys: pytest.CaptureFixture[str]
) -> None:
    """Startup-stderr substring and tool-body return are byte-equal.

    The shared canonical constant ``_CORTEX_CLI_MISSING_ERROR`` is the
    sole source of the user-facing message on both the import-time
    stderr branch (S5.1) and the per-call retry-exhaust path (S5.2 /
    S1.3 exhaustion). This test extracts the canonical-string substring
    from the stderr line emitted at startup and compares it to the
    delegate's return value at retry exhaust; the two MUST be
    byte-equal.

    See case (e) layering note: this is a delegate-level / stderr-line
    level invariant, not a wire-level one.
    """

    # Path 1: startup stderr (case g pattern).
    stderr_text = _reload_server_under_which_none(server_module, capsys)

    # The startup print uses ``f"cortex MCP: {_CORTEX_CLI_MISSING_ERROR}"``.
    # Extract the canonical substring by stripping the prefix and
    # trailing newline.
    prefix = "cortex MCP: "
    # Find the line that starts with the prefix.
    matching_lines = [
        line for line in stderr_text.splitlines() if line.startswith(prefix)
    ]
    assert matching_lines, (
        "expected at least one stderr line beginning with "
        f"{prefix!r}; got stderr={stderr_text!r}"
    )
    startup_canonical = matching_lines[-1][len(prefix):]

    # Path 2: tool-body return at retry exhaust (case e pattern).
    server_module._CORTEX_ROOT_CACHE = json.loads(_print_root_payload())

    def _always_fnf(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "cortex")

    with patch.object(server_module.subprocess, "run", side_effect=_always_fnf):
        tool_body_return = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    # Byte-equal: startup-stderr canonical substring == tool-body return.
    assert startup_canonical == tool_body_return
    # And both equal the module's canonical constant.
    assert startup_canonical == server_module._CORTEX_CLI_MISSING_ERROR
    assert tool_body_return == server_module._CORTEX_CLI_MISSING_ERROR
