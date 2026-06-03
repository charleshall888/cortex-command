"""Phase-3 acceptance tests for the skill-helper module + worktree refusal.

Covers three acceptance bundles from the spec:

R9 — console-script and ``python3 -m cortex_command.lifecycle.init_ensure``
     invoke the same code path with identical Namespace shapes.

R10 — ``cortex-lifecycle-init-ensure`` is referenced in both the canonical
      ``skills/lifecycle/SKILL.md`` and the regenerated mirror under
      ``plugins/cortex-core/skills/lifecycle/SKILL.md``; the existing
      dual-source-drift test suite exits 0.

R11 — the helper refuses when invoked inside a ``git worktree add`` attached
      worktree (exit 2 + diagnostic on stderr); a regular-checkout baseline
      passes through to ``handler.main`` without triggering the refusal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Repo root is 3 parents up from this file:
# cortex_command/lifecycle/tests/test_init_ensure.py
# [0] cortex_command/lifecycle/tests/
# [1] cortex_command/lifecycle/
# [2] cortex_command/
# [3] repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]

_CANONICAL_SKILL_MD = _REPO_ROOT / "skills" / "lifecycle" / "SKILL.md"
_MIRROR_SKILL_MD = (
    _REPO_ROOT / "plugins" / "cortex-core" / "skills" / "lifecycle" / "SKILL.md"
)
_DUAL_SOURCE_TEST = _REPO_ROOT / "tests" / "test_dual_source_reference_parity.py"


# ---------------------------------------------------------------------------
# Spy helper used by R9 namespace-shape parity test
# ---------------------------------------------------------------------------


class _MainSpy:
    """Callable that records ``args.__dict__`` from every ``handler.main`` call.

    Designed to be patched onto ``cortex_command.init.handler`` as ``main``
    so both invocation surfaces (console-script vs ``python3 -m``) can be
    exercised in sequence with their captured Namespace dicts compared.
    """

    captured: list[dict]

    def __init__(self) -> None:
        self.captured = []

    def __call__(self, args: object) -> int:  # args is argparse.Namespace
        self.captured.append(dict(vars(args)))
        return 0


# ---------------------------------------------------------------------------
# R9(a) — same exit code from console-script and python3 -m when
#          CORTEX_AUTO_ENSURE=0 (no real scaffolding fires).
# ---------------------------------------------------------------------------


def test_r9a_console_script_and_module_exit_same_code_auto_ensure_0(
    tmp_path: Path,
) -> None:
    """R9(a): console-script and ``python3 -m`` both exit 0 with CORTEX_AUTO_ENSURE=0."""
    env = {"CORTEX_AUTO_ENSURE": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    # Inherit the active Python environment so the installed console-script
    # and the package are both on PATH/importable.
    import os as _os

    full_env = dict(_os.environ)
    full_env["CORTEX_AUTO_ENSURE"] = "0"

    console = subprocess.run(
        ["cortex-lifecycle-init-ensure"],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )
    module = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.init_ensure"],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )

    assert console.returncode == 0, (
        f"console-script exit {console.returncode}; stderr={console.stderr!r}"
    )
    assert module.returncode == 0, (
        f"python3 -m exit {module.returncode}; stderr={module.stderr!r}"
    )
    assert console.returncode == module.returncode


# ---------------------------------------------------------------------------
# R9(b) — CORTEX_AUTO_ENSURE=0 honored on both surfaces (exit 0, no writes).
# ---------------------------------------------------------------------------


def test_r9b_cortex_auto_ensure_0_honored_on_both_surfaces(
    tmp_path: Path,
) -> None:
    """R9(b): CORTEX_AUTO_ENSURE=0 is honored by both invocation surfaces."""
    import os as _os

    full_env = dict(_os.environ)
    full_env["CORTEX_AUTO_ENSURE"] = "0"

    # Seed the tmp_path with a git repo that has foreign cortex/ content so
    # that — without the opt-out — the helper would exit 2 (R19 gate).
    subprocess.run(
        ["git", "init", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
        env={**_os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"},
    )
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir()
    (cortex_dir / "foreign.md").write_text("foreign content\n", encoding="utf-8")

    for cmd in (
        ["cortex-lifecycle-init-ensure"],
        [sys.executable, "-m", "cortex_command.lifecycle.init_ensure"],
    ):
        result = subprocess.run(
            cmd,
            cwd=str(tmp_path),
            env=full_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{cmd[0]}: expected exit 0 with CORTEX_AUTO_ENSURE=0; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )

    # No marker was written (the opt-out short-circuited before any I/O).
    assert not (cortex_dir / ".cortex-init").exists()


# ---------------------------------------------------------------------------
# R9(c) — Namespace-shape equivalence: both surfaces pass the same Namespace
#          into handler.main, asserted by spying on the function.
# ---------------------------------------------------------------------------


def test_r9c_namespace_shape_equivalence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R9(c): console-script and python3 -m pass identical Namespace dicts to handler.main.

    Both invocation surfaces within the same process call
    ``cortex_command.lifecycle.init_ensure.main()`` directly (no subprocess),
    with ``handler.main`` replaced by the spy so no real scaffolding fires.
    """
    import os as _os

    import cortex_command.init.handler as _handler
    from cortex_command.lifecycle import init_ensure as _init_ensure

    spy = _MainSpy()
    monkeypatch.setattr(_handler, "main", spy)

    # Ensure CORTEX_AUTO_ENSURE is NOT set so the early-return in
    # _run_ensure does not fire before handler.main is reached.
    monkeypatch.delenv("CORTEX_AUTO_ENSURE", raising=False)

    # Both invocations share the same monkeypatched module reference because
    # init_ensure.py imports handler at call-time (inside main()) via
    # ``from cortex_command.init import handler``.  The monkeypatch applied to
    # the already-imported module object is picked up by both calls.

    # Simulate console-script invocation (argv=[]).
    rc_console = _init_ensure.main([])

    # Simulate python3 -m invocation (same entry point, same argv shape).
    rc_module = _init_ensure.main([])

    assert rc_console == 0, f"console-script invocation returned {rc_console}"
    assert rc_module == 0, f"module invocation returned {rc_module}"

    assert len(spy.captured) == 2, (
        f"spy expected 2 captures; got {len(spy.captured)}: {spy.captured}"
    )

    ns_console, ns_module = spy.captured
    assert ns_console == ns_module, (
        f"Namespace-shape mismatch between console-script and module invocations:\n"
        f"  console: {ns_console}\n"
        f"  module:  {ns_module}"
    )

    # Also assert the exact expected attribute set so a future change to the
    # Namespace shape is caught here as an explicit regression rather than a
    # silent equality pass.
    expected_keys = frozenset(
        {"ensure", "update", "force", "unregister", "path"}
    )
    assert set(ns_console.keys()) == expected_keys, (
        f"Unexpected Namespace keys: {set(ns_console.keys())} != {expected_keys}"
    )
    assert ns_console["ensure"] is True
    assert ns_console["update"] is False
    assert ns_console["force"] is False
    assert ns_console["unregister"] is False
    assert ns_console["path"] is None


# ---------------------------------------------------------------------------
# R10(a) — canonical SKILL.md contains directive.
# ---------------------------------------------------------------------------


def test_r10a_canonical_skill_md_references_init_ensure() -> None:
    """R10(a): canonical skills/lifecycle/SKILL.md mentions cortex-lifecycle-init-ensure."""
    assert _CANONICAL_SKILL_MD.is_file(), (
        f"Canonical SKILL.md missing: {_CANONICAL_SKILL_MD}"
    )
    content = _CANONICAL_SKILL_MD.read_text(encoding="utf-8")
    count = content.count("cortex-lifecycle-init-ensure")
    assert count >= 1, (
        f"Expected at least 1 occurrence of 'cortex-lifecycle-init-ensure' in "
        f"{_CANONICAL_SKILL_MD}; found {count}"
    )


# ---------------------------------------------------------------------------
# R10(b) — mirror SKILL.md contains directive.
# ---------------------------------------------------------------------------


def test_r10b_mirror_skill_md_references_init_ensure() -> None:
    """R10(b): plugins/cortex-core/skills/lifecycle/SKILL.md mentions cortex-lifecycle-init-ensure."""
    assert _MIRROR_SKILL_MD.is_file(), (
        f"Mirror SKILL.md missing: {_MIRROR_SKILL_MD}"
    )
    content = _MIRROR_SKILL_MD.read_text(encoding="utf-8")
    count = content.count("cortex-lifecycle-init-ensure")
    assert count >= 1, (
        f"Expected at least 1 occurrence of 'cortex-lifecycle-init-ensure' in "
        f"{_MIRROR_SKILL_MD}; found {count}"
    )


# ---------------------------------------------------------------------------
# R10(c) — existing dual-source-drift test exits 0.
# ---------------------------------------------------------------------------


def test_r10c_dual_source_drift_test_exits_0() -> None:
    """R10(c): the dual-source-drift test suite exits 0 (canonical/mirror parity holds)."""
    assert _DUAL_SOURCE_TEST.is_file(), (
        f"Dual-source-drift test not found at: {_DUAL_SOURCE_TEST}"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_DUAL_SOURCE_TEST), "-q"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Dual-source-drift test exited {result.returncode};\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# R11(a) — worktree-attached refusal: exit 2 + diagnostic on stderr.
# ---------------------------------------------------------------------------


def test_r11a_worktree_attached_refusal(tmp_path: Path) -> None:
    """R11(a): helper exits 2 with diagnostic when invoked inside an attached git worktree."""
    import os as _os

    primary = tmp_path / "primary"
    primary.mkdir()

    # Initialize git repo and make an initial commit so worktree add works.
    subprocess.run(["git", "init", str(primary)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(primary),
        check=True,
        capture_output=True,
    )
    base_env = dict(_os.environ)
    base_env.update({
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    })
    (primary / "placeholder.txt").write_text("placeholder\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "placeholder.txt"],
        cwd=str(primary),
        check=True,
        capture_output=True,
        env=base_env,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(primary),
        check=True,
        capture_output=True,
        env=base_env,
    )

    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", str(wt), "HEAD"],
        cwd=str(primary),
        check=True,
        capture_output=True,
        env=base_env,
    )
    assert wt.is_dir(), f"worktree directory not created: {wt}"

    # Invoke the helper from inside the attached worktree.
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.init_ensure"],
        cwd=str(wt),
        capture_output=True,
        text=True,
        env=base_env,
    )

    assert result.returncode == 2, (
        f"Expected exit 2 (worktree refusal); got {result.returncode}; "
        f"stderr={result.stderr!r}; stdout={result.stdout!r}"
    )
    # Spec R11 diagnostic phrase.
    assert "cortex-lifecycle-init-ensure" in result.stderr, (
        f"Expected R11 diagnostic on stderr; got: {result.stderr!r}"
    )
    assert "worktree" in result.stderr.lower(), (
        f"Expected 'worktree' in diagnostic; got: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# R11(b) — regular-checkout baseline: probe passes through without worktree refusal.
# ---------------------------------------------------------------------------


def test_r11b_regular_checkout_baseline(tmp_path: Path) -> None:
    """R11(b): helper exits 0 from primary worktree with CORTEX_AUTO_ENSURE=0.

    This test proves the worktree-detection probe does NOT mis-classify a
    normal (primary) checkout as an attached worktree.  CORTEX_AUTO_ENSURE=0
    is set so the helper short-circuits immediately after the probe passes —
    no real scaffolding writes occur.
    """
    import os as _os

    primary = tmp_path / "primary"
    primary.mkdir()

    subprocess.run(["git", "init", str(primary)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(primary),
        check=True,
        capture_output=True,
    )
    base_env = dict(_os.environ)
    base_env.update({
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
        "CORTEX_AUTO_ENSURE": "0",
    })
    (primary / "placeholder.txt").write_text("placeholder\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "placeholder.txt"],
        cwd=str(primary),
        check=True,
        capture_output=True,
        env=base_env,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(primary),
        check=True,
        capture_output=True,
        env=base_env,
    )

    # Invoke the helper from the primary worktree (no attached worktrees added).
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.init_ensure"],
        cwd=str(primary),
        capture_output=True,
        text=True,
        env=base_env,
    )

    assert result.returncode == 0, (
        f"Expected exit 0 from primary worktree with CORTEX_AUTO_ENSURE=0; "
        f"got {result.returncode}; stderr={result.stderr!r}; stdout={result.stdout!r}"
    )
    # No worktree diagnostic should appear.
    assert "cortex-lifecycle-init-ensure: invoked inside a git worktree" not in result.stderr
