"""Phase-1 regression guards for the launcher↔CLI argv contract (R1, R2).

Two platform-agnostic guards (NOT ``skipUnless(darwin)``) that pin the
load-bearing ADR-0007 move: the launchd launcher invokes
``cortex overnight start`` WITHOUT ``--launchd``, routing through the
run-now async-spawn path so the runner becomes the surviving session
leader.

  * ``TestLauncherArgvRender`` (R1): renders the real launcher template
    via :meth:`MacOSLaunchAgentBackend._install_launcher_script` (with a
    monkeypatched ``_resolve_cortex_bin``), tokenizes the emitted cortex
    invocation line, and asserts it parses under the real ``start``
    subparser (no ``SystemExit``), carries the required flag set
    (``--state <abs>``, ``--format json``, ``--force``), and does NOT
    carry the forbidden flags (``--session-id``, ``--launchd``). A
    later-added ``--scheduled`` (Task 5 wiring) is permitted — we assert
    on the forbidden set, not an exhaustive allowlist.

  * ``TestLauncherArgvRouting`` (R2 join): parses that SAME launcher
    argv and asserts ``handle_start`` dispatches to the async-spawn path
    (:func:`_spawn_runner_async`), NOT the inline ``--launchd`` path
    (:func:`_run_runner_inline`). This is the join that ties the
    no-``--launchd`` launcher argv to the session-leader behavior — a
    bare string check (R1) and a session check on a possibly-faked spawn
    (R2 ``os.getsid``) do not, by themselves, prove the launcher routes
    to the async-spawn path; this branch assertion closes that gap.

These run via ``just test`` anywhere the suite runs. They are NOT wired
into GitHub Actions today (``validate.yml`` runs only skill + callgraph
validators); CI-wiring is an out-of-scope follow-up.
"""

from __future__ import annotations

import shlex
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cortex_command.cli import _build_parser
from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend


# ---------------------------------------------------------------------------
# Shared rendering + argv-extraction helpers
# ---------------------------------------------------------------------------


def _render_launcher(*, session_dir: Path, cortex_bin: str) -> str:
    """Render the real launcher template and return its text.

    Patches :func:`_resolve_cortex_bin` so ``@@CORTEX_BIN@@`` is replaced
    with ``cortex_bin`` rather than whatever ``shutil.which("cortex")``
    returns on the host.
    """
    backend = MacOSLaunchAgentBackend()
    plist_path = session_dir.parent / "fake.plist"
    launcher_path = session_dir.parent / "launcher.sh"
    with patch(
        "cortex_command.overnight.scheduler.macos._resolve_cortex_bin",
        return_value=cortex_bin,
    ):
        backend._install_launcher_script(
            launcher_path=launcher_path,
            plist_path=plist_path,
            session_dir_=session_dir,
            label="com.charleshall.cortex-command.overnight-schedule.s1.111",
            session_id="s1",
            repo_root=Path("/repo"),
        )
    return launcher_path.read_text(encoding="utf-8")


def _extract_start_argv(
    launcher_text: str, *, session_dir: Path, cortex_bin: str
) -> list[str]:
    """Tokenize the launcher's ``cortex overnight start`` invocation.

    Joins the backslash-continued invocation lines, drops the shell
    redirections (``</dev/null``, ``2>>...``), resolves the bash
    variables the launcher sets (``${CORTEX_BIN}``, ``${SESSION_DIR}``,
    ``${STATE_PATH}``), and returns the argv tokens AFTER
    ``cortex overnight start`` — i.e. the flag list to feed the
    ``start`` subparser.
    """
    # Find the invocation block: starts at the line containing the
    # CORTEX_BIN call, continues across backslash line-continuations.
    lines = launcher_text.splitlines()
    start_idx = next(
        i
        for i, ln in enumerate(lines)
        if '"${CORTEX_BIN}"' in ln and "overnight start" in ln
    )
    block_lines: list[str] = []
    idx = start_idx
    while True:
        raw = lines[idx]
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            block_lines.append(stripped[:-1])
            idx += 1
            continue
        block_lines.append(stripped)
        break
    block = " ".join(block_lines)

    # Resolve the bash variables the launcher defines. STATE_PATH is
    # derived as "${SESSION_DIR}/overnight-state.json" in the template,
    # so substitute it first, then SESSION_DIR / CORTEX_BIN.
    state_path = f"{session_dir}/overnight-state.json"
    block = block.replace("${STATE_PATH}", state_path)
    block = block.replace("${SESSION_DIR}", str(session_dir))
    block = block.replace("${CORTEX_BIN}", cortex_bin)

    tokens = shlex.split(block)

    # Strip shell redirections — shlex keeps them as bare tokens.
    cleaned: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok == "</dev/null":
            continue
        if tok.startswith("2>>") or tok.startswith(">>") or tok.startswith("2>"):
            continue
        if tok in ("<", ">", ">>", "2>", "2>>"):
            skip_next = True
            continue
        cleaned.append(tok)

    # Drop the binary path and the ``overnight start`` words; what
    # remains is the start-subparser argv.
    assert cleaned[0] == cortex_bin, cleaned
    assert cleaned[1] == "overnight", cleaned
    assert cleaned[2] == "start", cleaned
    return cleaned[3:]


# ---------------------------------------------------------------------------
# R1 — launcher-argv render test
# ---------------------------------------------------------------------------


class TestLauncherArgvRender(unittest.TestCase):
    """The rendered launcher emits a valid, complete no-``--launchd`` argv."""

    def test_emitted_start_argv_parses_and_has_required_flags(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            session_dir = tmp / "sessions" / "s1"
            session_dir.mkdir(parents=True)
            cortex_bin = str(tmp / "cortex-stub")

            launcher_text = _render_launcher(
                session_dir=session_dir, cortex_bin=cortex_bin
            )
            argv = _extract_start_argv(
                launcher_text, session_dir=session_dir, cortex_bin=cortex_bin
            )

            # (a) Parses under the start subparser with no SystemExit.
            parser = _build_parser()
            try:
                ns = parser.parse_args(["overnight", "start", *argv])
            except SystemExit as exc:  # pragma: no cover - failure path
                self.fail(
                    f"launcher argv failed to parse under start subparser "
                    f"(SystemExit {exc.code}); argv={argv!r}"
                )

            self.assertEqual(ns.command, "overnight")
            self.assertEqual(ns.overnight_command, "start")

            # (b) Required flags present.
            self.assertIn("--state", argv, f"missing --state in {argv!r}")
            state_val = argv[argv.index("--state") + 1]
            self.assertTrue(
                Path(state_val).is_absolute(),
                f"--state value is not absolute: {state_val!r}",
            )
            self.assertEqual(ns.state, state_val)

            self.assertEqual(
                ns.format, "json", f"--format json not parsed; argv={argv!r}"
            )
            # Confirm the literal flag pair is present (not just a default).
            self.assertIn("--format", argv)
            self.assertEqual(argv[argv.index("--format") + 1], "json")

            self.assertTrue(ns.force, f"--force not set; argv={argv!r}")
            self.assertIn("--force", argv)

            # (c) Forbidden flags absent. Assert on the forbidden SET so a
            # later-added --scheduled (Task 5) does not break this guard.
            self.assertNotIn(
                "--session-id", argv, f"--session-id leaked into {argv!r}"
            )
            self.assertNotIn(
                "--launchd", argv, f"--launchd leaked into {argv!r}"
            )
            # --launchd must also not have parsed to a truthy attr.
            self.assertFalse(getattr(ns, "launchd", False))


# ---------------------------------------------------------------------------
# R2 join — routing test
# ---------------------------------------------------------------------------


class TestLauncherArgvRouting(unittest.TestCase):
    """The launcher argv routes ``handle_start`` to the async-spawn path.

    Parses the SAME launcher-emitted argv and asserts ``handle_start``
    dispatches to :func:`_spawn_runner_async` (the run-now,
    ``start_new_session=True`` session-leader path), NOT the inline
    ``--launchd`` path (:func:`_run_runner_inline`). Both are spied so
    the test asserts which branch was taken for the real no-``--launchd``
    argv — the join that ties R1 (argv string) to R2 (session leader).
    """

    def test_launcher_argv_routes_to_async_spawn_not_inline(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            session_dir = tmp / "sessions" / "s1"
            session_dir.mkdir(parents=True)
            cortex_bin = str(tmp / "cortex-stub")

            # A loadable state file at the launcher's --state path so
            # handle_start clears the existence guard and reaches routing.
            state_path = session_dir / "overnight-state.json"
            state_path.write_text(
                '{"session_id": "s1", "phase": "executing", '
                '"plan_ref": "cortex/lifecycle/overnight-plan.md", '
                '"current_round": 1, '
                '"started_at": "2026-04-26T00:00:00+00:00", '
                '"updated_at": "2026-04-26T00:00:00+00:00", '
                '"features": {}}',
                encoding="utf-8",
            )

            launcher_text = _render_launcher(
                session_dir=session_dir, cortex_bin=cortex_bin
            )
            argv = _extract_start_argv(
                launcher_text, session_dir=session_dir, cortex_bin=cortex_bin
            )

            parser = _build_parser()
            ns = parser.parse_args(["overnight", "start", *argv])

            # Spy both candidate branch targets. The async-spawn spy
            # returns a started envelope so handle_start completes 0; the
            # inline spy fails loudly if the wrong branch is taken.
            spawn_calls: list = []

            def fake_spawn(**kwargs):  # type: ignore[no-untyped-def]
                spawn_calls.append(kwargs)
                return {
                    "started": True,
                    "session_id": "s1",
                    "pid": 4242,
                }

            def fail_inline(**kwargs):  # type: ignore[no-untyped-def]
                raise AssertionError(
                    "launcher argv took the inline --launchd path; it must "
                    "route through _spawn_runner_async (async-spawn) so the "
                    "runner becomes the surviving session leader"
                )

            with patch.object(
                cli_handler, "_spawn_runner_async", fake_spawn
            ), patch.object(
                cli_handler, "_run_runner_inline", fail_inline
            ), patch.object(
                cli_handler, "_resolve_repo_path", return_value=tmp
            ):
                rc = cli_handler.handle_start(ns)

            self.assertEqual(rc, 0)
            self.assertEqual(
                len(spawn_calls),
                1,
                "handle_start did not dispatch to _spawn_runner_async exactly "
                "once for the no---launchd launcher argv",
            )


if __name__ == "__main__":
    unittest.main()
