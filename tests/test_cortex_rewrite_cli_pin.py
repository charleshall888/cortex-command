"""Unit tests for ``bin/cortex-rewrite-cli-pin`` (spec R19.5).

The acceptance criterion calls for ≥8 PASSED lines covering: single-line
tuple form, multi-line tuple form, single-quote variant, idempotent no-op,
zero-matches (fail), two-matches (fail), CLI_PIN moved to a different line
than 105 (pattern still finds it), and CLI_PIN[1] preserved across rewrites.

The tests are split between pure-logic tests against ``rewrite_text`` /
``find_cli_pin_matches`` (fast, no git, no filesystem) and fixture-replay
tests that exercise the read-modify-write + post-rewrite git diff path
end-to-end in a real (tmp) git repo.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-rewrite-cli-pin"


def _load_script_module():
    """Load the script as an importable module for direct function tests.

    The script lacks a ``.py`` extension (it's a deployed bin/ command), so
    we instantiate the source-file loader explicitly rather than relying on
    ``spec_from_file_location``'s extension-based suffix dispatch (which
    returns ``None`` for non-``.py`` paths).
    """
    loader = importlib.machinery.SourceFileLoader(
        "cortex_rewrite_cli_pin", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MOD = _load_script_module()


# ---------------------------------------------------------------------------
# Pure-logic tests (find_cli_pin_matches / rewrite_text)
# ---------------------------------------------------------------------------


def test_single_line_tuple_form_matches_and_rewrites():
    """Canonical single-line form: ``CLI_PIN = ("v0.1.0", "2.0")``."""
    text = '#: prelude\nCLI_PIN = ("v0.1.0", "2.0")\n# trailing\n'
    matches = MOD.find_cli_pin_matches(text)
    assert len(matches) == 1
    new_text, old_tag, schema = MOD.rewrite_text(text, "v2.0.0")
    assert old_tag == "v0.1.0"
    assert schema == "2.0"
    assert 'CLI_PIN = ("v2.0.0", "2.0")' in new_text
    assert "v0.1.0" not in new_text


def test_multi_line_tuple_form_matches_and_rewrites():
    """Multi-line form with newlines inside the parens."""
    text = (
        "# pre\n"
        "CLI_PIN = (\n"
        '    "v1.0.2",\n'
        '    "2.0",\n'
        ")\n"
        "# post\n"
    )
    matches = MOD.find_cli_pin_matches(text)
    assert len(matches) == 1
    new_text, old_tag, schema = MOD.rewrite_text(text, "v2.0.0")
    assert old_tag == "v1.0.2"
    assert schema == "2.0"
    # The rewriter collapses to canonical single-line form using the original
    # quote chars; the new tag must appear and the old tag must not.
    assert "v2.0.0" in new_text
    assert "v1.0.2" not in new_text
    # Schema preserved verbatim.
    assert '"2.0"' in new_text


def test_single_quote_variant_matches_and_rewrites():
    """Single-quoted strings inside the tuple are accepted (format tolerance)."""
    text = "CLI_PIN = ('v0.5.0', '1.2')\n"
    matches = MOD.find_cli_pin_matches(text)
    assert len(matches) == 1
    new_text, old_tag, schema = MOD.rewrite_text(text, "v0.5.1")
    assert old_tag == "v0.5.0"
    assert schema == "1.2"
    # Preserves single-quote form for both elements.
    assert "CLI_PIN = ('v0.5.1', '1.2')" in new_text


def test_zero_matches_raises_value_error():
    """No CLI_PIN declaration → ``rewrite_text`` raises ValueError."""
    text = "# this file has no CLI_PIN declaration at all\nfoo = 1\n"
    assert MOD.find_cli_pin_matches(text) == []
    with pytest.raises(ValueError, match="found 0"):
        MOD.rewrite_text(text, "v2.0.0")


def test_two_matches_raises_value_error():
    """Two CLI_PIN declarations → ``rewrite_text`` raises ValueError."""
    text = (
        'CLI_PIN = ("v0.1.0", "2.0")\n'
        "# duplicate (comment-shaped real declaration to simulate the failure):\n"
        'CLI_PIN = ("v0.2.0", "2.0")\n'
    )
    matches = MOD.find_cli_pin_matches(text)
    assert len(matches) == 2
    with pytest.raises(ValueError, match="found 2"):
        MOD.rewrite_text(text, "v3.0.0")


def test_pattern_finds_cli_pin_at_non_default_line():
    """Pattern is line-anchored to ``^CLI_PIN``, not line 105.

    Per spec contract (i) the regex must be anchored on ``^CLI_PIN\\s*=\\s*\\(``
    at start of line and NOT depend on the literal living at any specific
    line number. This test plants the literal at a different position to
    verify the pattern still matches.
    """
    # Pad with many lines above CLI_PIN to ensure the line number differs
    # from the canonical 105.
    padding = "\n".join(f"# header line {i}" for i in range(200))
    text = padding + '\nCLI_PIN = ("v0.1.0", "2.0")\n'
    matches = MOD.find_cli_pin_matches(text)
    assert len(matches) == 1, "pattern must match regardless of line number"
    new_text, _, _ = MOD.rewrite_text(text, "v2.0.0")
    assert "v2.0.0" in new_text
    assert "v0.1.0" not in new_text


def test_cli_pin_schema_preserved_across_rewrite():
    """Contract (iii): the rewriter MUST preserve the existing CLI_PIN[1].

    Non-default schema value ("1.5") must round-trip unchanged.
    """
    text = 'CLI_PIN = ("v0.1.0", "1.5")\n'
    new_text, old_tag, schema = MOD.rewrite_text(text, "v2.0.0")
    assert old_tag == "v0.1.0"
    assert schema == "1.5"
    # The schema literal must survive the rewrite verbatim.
    assert '"1.5"' in new_text
    # And no other schema value sneaked in.
    assert '"2.0"' not in new_text


# ---------------------------------------------------------------------------
# Fixture-replay tests (real git repo, real subprocess invocation)
# ---------------------------------------------------------------------------


def _init_git_repo(tmp_path: Path) -> None:
    """Init a minimal git repo at ``tmp_path``. Quiet, no signing."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"],
        check=True, env=env,
    )


def _commit_initial(tmp_path: Path, rel_path: str, content: str) -> None:
    """Write ``content`` to ``rel_path`` under tmp_path and commit it."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", rel_path],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "initial"],
        check=True, env=env,
    )


def _run_script(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the helper script with cwd=tmp_path."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    env.pop("LIFECYCLE_SESSION_ID", None)
    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=str(tmp_path), capture_output=True, text=True, env=env,
    )


def test_script_idempotent_on_no_op(tmp_path: Path):
    """Contract (v): invoking with a tag equal to CLI_PIN[0] is a no-op.

    Exit code 0; file unmodified (no diff).
    """
    _init_git_repo(tmp_path)
    rel_path = "plugins/cortex-overnight/server.py"
    initial = 'CLI_PIN = ("v0.1.0", "2.0")\n'
    _commit_initial(tmp_path, rel_path, initial)
    result = _run_script(tmp_path, "v0.1.0")
    assert result.returncode == 0, result.stderr
    # File must be unchanged.
    assert (tmp_path / rel_path).read_text(encoding="utf-8") == initial


def test_script_rewrites_and_passes_diff_verification(tmp_path: Path):
    """Happy path end-to-end: rewrite + git diff verification both succeed."""
    _init_git_repo(tmp_path)
    rel_path = "plugins/cortex-overnight/server.py"
    initial = (
        "# prelude\n"
        '#: comment about the pin\n'
        'CLI_PIN = ("v0.1.0", "2.0")\n'
        "# trailing\n"
    )
    _commit_initial(tmp_path, rel_path, initial)
    result = _run_script(tmp_path, "v2.0.0")
    assert result.returncode == 0, result.stderr
    after = (tmp_path / rel_path).read_text(encoding="utf-8")
    assert 'CLI_PIN = ("v2.0.0", "2.0")' in after
    assert "v0.1.0" not in after


def test_script_fails_on_zero_matches(tmp_path: Path):
    """Contract (iv): zero CLI_PIN declarations → non-zero exit, clear message."""
    _init_git_repo(tmp_path)
    rel_path = "plugins/cortex-overnight/server.py"
    initial = "# this file has no CLI_PIN at all\nfoo = 1\n"
    _commit_initial(tmp_path, rel_path, initial)
    result = _run_script(tmp_path, "v2.0.0")
    assert result.returncode != 0
    assert "found 0" in result.stderr
    # File must be unchanged.
    assert (tmp_path / rel_path).read_text(encoding="utf-8") == initial


def test_script_fails_on_two_matches(tmp_path: Path):
    """Contract (iv): two CLI_PIN declarations → non-zero exit, clear message."""
    _init_git_repo(tmp_path)
    rel_path = "plugins/cortex-overnight/server.py"
    initial = (
        'CLI_PIN = ("v0.1.0", "2.0")\n'
        "# duplicate (real second declaration to trip the guard):\n"
        'CLI_PIN = ("v0.2.0", "2.0")\n'
    )
    _commit_initial(tmp_path, rel_path, initial)
    result = _run_script(tmp_path, "v2.0.0")
    assert result.returncode != 0
    assert "found 2" in result.stderr
    # File must be unchanged.
    assert (tmp_path / rel_path).read_text(encoding="utf-8") == initial


def test_script_invalid_tag_form_rejected(tmp_path: Path):
    """Tag must match vX.Y.Z; malformed input is rejected before any I/O."""
    _init_git_repo(tmp_path)
    rel_path = "plugins/cortex-overnight/server.py"
    initial = 'CLI_PIN = ("v0.1.0", "2.0")\n'
    _commit_initial(tmp_path, rel_path, initial)
    result = _run_script(tmp_path, "not-a-tag")
    assert result.returncode != 0
    assert "invalid tag" in result.stderr
    # File must be unchanged.
    assert (tmp_path / rel_path).read_text(encoding="utf-8") == initial
