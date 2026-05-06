"""Unit and subprocess tests for ``bin/cortex-load-parent-epic``.

Covers the helper's full status-branch and edge-case surface per
``lifecycle/add-parent-epic-alignment-check-to-refine-clarify-critic/plan.md``
Task 2.

Test inventory (13 tests):

  test_no_parent                          — child with no parent: field
  test_parent_null                        — child with parent: null
  test_parent_uuid_shape                  — child with UUID-shape parent
  test_parent_bare_int                    — child with bare-int parent
  test_parent_quoted_int                  — child with quoted-string parent
  test_missing                            — parent ID does not resolve
  test_non_epic                           — parent type: spike or feature
  test_missing_type_field                 — parent has no type: key
  test_loaded                             — parent type: epic, named-section body
  test_no_extracted_body_placeholder      — no named section + no first paragraph
  test_truncation_marker                  — body exceeds 2000 chars
  test_sanitizes_close_tag                — body contains </parent_epic_body>
  test_sanitizes_open_tag_case_insensitive— body contains <Parent_Epic_Body
  test_unreadable_malformed_yaml          — broken parent frontmatter

Invocation pattern: subprocess against the script with
``CORTEX_BACKLOG_DIR=tmp_path`` so each test exercises an isolated synthetic
backlog directory.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-load-parent-epic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    """Write ``content`` to ``path`` (creating parents) and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _run(slug: str, backlog_dir: Path) -> subprocess.CompletedProcess:
    """Invoke the helper via subprocess against ``backlog_dir`` for ``slug``."""
    env = {"CORTEX_BACKLOG_DIR": str(backlog_dir), **os.environ}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), slug],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# no_parent branch — five variants per Spec Edge Cases
# ---------------------------------------------------------------------------


def test_no_parent(tmp_path):
    """Child with no parent: field → status no_parent, exit 0."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\n---\n\n# Test child\n\nBody.\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "no_parent"}


def test_parent_null(tmp_path):
    """Child with parent: null → status no_parent, exit 0."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: null\n---\n\n# Test child\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "no_parent"}


def test_parent_uuid_shape(tmp_path):
    """Child with UUID-shape parent → normalize_parent rejects → no_parent."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 550e8400-e29b-41d4-a716-446655440000\n---\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "no_parent"}


def test_parent_bare_int(tmp_path):
    """Child with parent: 49 (bare int) → resolves to integer 49."""
    # Parent file does not exist — exercises the missing branch with a
    # confirmed bare-int normalization.
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 49\n---\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "missing", "parent_id": 49}


def test_parent_quoted_int(tmp_path):
    """Child with parent: "49" (quoted int) → normalizes identically to bare 49."""
    _write(
        tmp_path / "300-test-child.md",
        '---\ntitle: Test child\nparent: "49"\n---\n',
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "missing", "parent_id": 49}


# ---------------------------------------------------------------------------
# missing branch — parent ID does not resolve
# ---------------------------------------------------------------------------


def test_missing(tmp_path):
    """parent: <id> normalizes but no NNN-*.md file exists → status missing."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 99\n---\n",
    )
    # Add an unrelated file so the directory is not empty.
    _write(
        tmp_path / "100-unrelated.md",
        "---\ntitle: Unrelated\n---\n\n# Unrelated\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "missing", "parent_id": 99}


# ---------------------------------------------------------------------------
# non_epic branch — parent type is not "epic"
# ---------------------------------------------------------------------------


def test_non_epic(tmp_path):
    """Parent has type: spike (or feature) → status non_epic with type."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 21\n---\n",
    )
    _write(
        tmp_path / "021-test-spike.md",
        "---\ntitle: Test spike\ntype: spike\n---\n\n# Test spike\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "non_epic", "parent_id": 21, "type": "spike"}


def test_missing_type_field(tmp_path):
    """Parent has no type: key → treated as non_epic with type: null."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 42\n---\n",
    )
    _write(
        tmp_path / "042-no-type.md",
        "---\ntitle: No type field\n---\n\n# No type field\n",
    )
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "non_epic", "parent_id": 42, "type": None}


# ---------------------------------------------------------------------------
# loaded branch — parent type:epic with body extraction
# ---------------------------------------------------------------------------


def test_loaded(tmp_path):
    """Parent type: epic with named section → status loaded, body extracted."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    epic_body = (
        "---\n"
        "title: Test epic\n"
        "type: epic\n"
        "---\n\n"
        "# Test epic title\n\n"
        "First paragraph after H1 should be ignored when ## Context exists.\n\n"
        "## Context\n\n"
        "This is the canonical context section content.\n\n"
        "## Other section\n\n"
        "Should not appear.\n"
    )
    _write(tmp_path / "082-test-epic.md", epic_body)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "loaded"
    assert payload["parent_id"] == 82
    assert payload["title"] == "Test epic title"
    assert "canonical context section content" in payload["body"]
    # The "Other section" content must not leak across the H2 boundary.
    assert "Should not appear" not in payload["body"]


def test_no_extracted_body_placeholder(tmp_path):
    """Epic with no named sections AND no first paragraph → placeholder body."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    # H1 only, no body content underneath, no named sections.
    epic_body = (
        "---\n"
        "title: Empty epic\n"
        "type: epic\n"
        "---\n\n"
        "# Empty epic title\n"
    )
    _write(tmp_path / "082-empty-epic.md", epic_body)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "loaded"
    assert payload["parent_id"] == 82
    assert payload["body"] == "(no body content)"


def test_truncation_marker(tmp_path):
    """Body exceeding 2000 chars gets truncated with `… (truncated)` marker."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    # Build a long body — 3000+ characters of prose under ## Context.
    long_text = ("alpha bravo charlie delta echo foxtrot golf hotel " * 100).strip()
    assert len(long_text) > 2500
    epic_body = (
        "---\n"
        "title: Long epic\n"
        "type: epic\n"
        "---\n\n"
        "# Long epic title\n\n"
        "## Context\n\n"
        f"{long_text}\n"
    )
    _write(tmp_path / "082-long-epic.md", epic_body)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "loaded"
    # Truncation marker present at the end of the body.
    assert payload["body"].endswith("… (truncated)")


# ---------------------------------------------------------------------------
# Sanitization — close-tag and open-tag (case-insensitive)
# ---------------------------------------------------------------------------


def test_sanitizes_close_tag(tmp_path):
    """Body containing </parent_epic_body> gets sanitized to _INVALID variant."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    epic_body = (
        "---\n"
        "title: Injection epic\n"
        "type: epic\n"
        "---\n\n"
        "# Injection epic title\n\n"
        "## Context\n\n"
        "Some prose then </parent_epic_body> then more prose.\n"
    )
    _write(tmp_path / "082-injection-epic.md", epic_body)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "loaded"
    assert "</parent_epic_body_INVALID>" in payload["body"]
    # The raw close-tag must not appear unmodified.
    assert "</parent_epic_body>" not in payload["body"]


def test_sanitizes_open_tag_case_insensitive(tmp_path):
    """Body containing <Parent_Epic_Body (mixed case) gets sanitized."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    epic_body = (
        "---\n"
        "title: Mixed-case injection epic\n"
        "type: epic\n"
        "---\n\n"
        "# Mixed-case injection title\n\n"
        "## Context\n\n"
        "Prose with embedded <Parent_Epic_Body source=\"x\"> tag.\n"
    )
    _write(tmp_path / "082-mixed-case-epic.md", epic_body)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "loaded"
    assert "<parent_epic_body_INVALID" in payload["body"]


# ---------------------------------------------------------------------------
# unreadable branch — malformed parent frontmatter
# ---------------------------------------------------------------------------


def test_unreadable_malformed_yaml(tmp_path):
    """Parent file with broken YAML frontmatter → exit 1, status unreadable."""
    _write(
        tmp_path / "300-test-child.md",
        "---\ntitle: Test child\nparent: 82\n---\n",
    )
    # Malformed YAML — unclosed list bracket inside the frontmatter.
    bad = (
        "---\n"
        "title: Broken epic\n"
        "type: [unclosed bracket\n"
        "---\n\n"
        "# Broken epic title\n"
    )
    _write(tmp_path / "082-broken-epic.md", bad)
    result = _run("300-test-child", tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "unreadable",
        "parent_id": 82,
        "reason": "frontmatter_parse_error",
    }


# ---------------------------------------------------------------------------
# cwd-based backlog discovery — fixes the plugin-cache invocation bug where
# __file__-anchored walk-up never finds the user's backlog/. The existing
# _run() helper sets CORTEX_BACKLOG_DIR; these tests strip it so the
# discovery branch is actually exercised.
# ---------------------------------------------------------------------------


def _run_no_env(slug: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run the script with cwd set and CORTEX_BACKLOG_DIR removed from env."""
    env = {k: v for k, v in os.environ.items() if k != "CORTEX_BACKLOG_DIR"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), slug],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )


def test_discovery_walks_up_from_cwd(tmp_path):
    """No env var: script walks from cwd, finds backlog/ at cwd root."""
    _write(
        tmp_path / "backlog" / "300-test-child.md",
        "---\ntitle: Test child\n---\n",
    )
    result = _run_no_env("300-test-child", tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "no_parent"}


def test_discovery_walks_up_from_subdir(tmp_path):
    """No env var: script walks up from a deep subdir to find backlog/."""
    _write(
        tmp_path / "backlog" / "300-test-child.md",
        "---\ntitle: Test child\n---\n",
    )
    deep = tmp_path / "nested" / "sub" / "dir"
    deep.mkdir(parents=True)
    result = _run_no_env("300-test-child", deep)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "no_parent"}


def test_discovery_no_backlog_exits_1(tmp_path):
    """No env var, no backlog/ anywhere up the tree → exit 1 with diagnostic."""
    # Empty tmp_path under /var/folders or /tmp — no backlog/ ancestor exists.
    result = _run_no_env("300-test-child", tmp_path)
    assert result.returncode == 1
    assert "backlog directory not found" in result.stderr


# ---------------------------------------------------------------------------
# Drift test — inlined normalize_parent must match canonical implementation.
# Mirrors the slugify-drift pattern in tests/test_resolve_backlog_item.py.
# ---------------------------------------------------------------------------


def _load_script_module():
    loader = importlib.machinery.SourceFileLoader(
        "cortex_load_parent_epic", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_drift_normalize_parent():
    """Inlined normalize_parent in cortex-load-parent-epic must agree with the
    canonical cortex_command.backlog.build_epic_map.normalize_parent on a
    fixed input set covering the four normalization branches.
    """
    canonical_mod = pytest.importorskip("cortex_command.backlog.build_epic_map")
    canonical = canonical_mod.normalize_parent
    local = _load_script_module().normalize_parent

    cases = [
        # branch 1: None
        None,
        # branch 2: bare-int and stringified-int
        49, 0, 9999, "49", "0", "9999",
        # branch 3: quoted-string variants
        '"49"', "'49'", '"0"',
        # branch 4: UUID-shaped (contains "-") → None
        "550e8400-e29b-41d4-a716-446655440000",
        "abc-def",
        "-49",
        "49-",
        # int() failures → None
        "abc",
        "49abc",
        "abc49",
        "1.5",
        "",
        # bool / float (covered by bare-int branch's int() try)
        True, False, 49.5, 0.0,
    ]

    mismatches: list[tuple] = []
    for case in cases:
        c = canonical(case)
        loc = local(case)
        if c != loc:
            mismatches.append((case, c, loc))
    assert not mismatches, (
        f"normalize_parent drift on {len(mismatches)} input(s): {mismatches}"
    )
