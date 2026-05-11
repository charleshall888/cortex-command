"""Path-validation tests for ``cortex_command.critical_review`` (Req 9).

Covers the Requirement 9 path-validation gate at TWO layers:

  1. Module API — direct calls to ``validate_artifact_path`` / ``prepare_dispatch``:
       (a) symlink rejection (Req 9d)
       (b) out-of-prefix rejection
       (c) feature-narrowing acceptance + rejection
       (d) ``lifecycle_root`` itself rejected (strict prefix)
       (e) valid path returns realpath

  2. CLI subprocess — ``python3 -m cortex_command.critical_review``:
       (f) symlink rejected end-to-end (non-zero exit + stderr message)
       (g) valid path returns exit 0 + JSON on stdout

Each scenario is its own ``def test_*`` for granular failure reporting.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.critical_review import (
    prepare_dispatch,
    validate_artifact_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lifecycle_layout(tmp_path: Path) -> dict:
    """Build a minimal ``lifecycle/foo/`` tree with a real file and a symlink.

    Returns a dict with keys:
        lifecycle_root: tmp_path/'lifecycle'
        feature_dir:    tmp_path/'lifecycle'/'foo'
        good_file:      tmp_path/'lifecycle'/'foo'/'spec.md' (regular file)
        evil_symlink:   tmp_path/'lifecycle'/'foo'/'evil.md' -> /etc/hostname
        outside_file:   tmp_path/'outside.md' (regular file, not under lifecycle)
    """
    lifecycle_root = tmp_path / "lifecycle"
    feature_dir = lifecycle_root / "foo"
    feature_dir.mkdir(parents=True)

    good_file = feature_dir / "spec.md"
    good_file.write_text("hello world\n", encoding="utf-8")

    evil_symlink = feature_dir / "evil.md"
    evil_symlink.symlink_to("/etc/hostname")

    outside_file = tmp_path / "outside.md"
    outside_file.write_text("not under lifecycle\n", encoding="utf-8")

    return {
        "lifecycle_root": lifecycle_root,
        "feature_dir": feature_dir,
        "good_file": good_file,
        "evil_symlink": evil_symlink,
        "outside_file": outside_file,
    }


# ---------------------------------------------------------------------------
# (1) Module API tests
# ---------------------------------------------------------------------------


def test_module_api_rejects_symlink_with_realpath_in_message(lifecycle_layout: dict) -> None:
    """Req 9d: symlink under lifecycle/ is rejected; message names the path and realpath."""
    evil = lifecycle_layout["evil_symlink"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(evil), str(root))
    msg = str(exc_info.value)
    # Message must name the offending path.
    assert str(evil) in msg or "evil.md" in msg
    # Message must name the realpath target (the symlink resolved to /etc/hostname).
    assert "/etc/hostname" in msg or "realpath" in msg


def test_module_api_rejects_path_outside_lifecycle_root(lifecycle_layout: dict) -> None:
    """Req 9b: path outside lifecycle/ is rejected; message names the allowed prefix."""
    outside = lifecycle_layout["outside_file"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(outside), str(root))
    msg = str(exc_info.value)
    # Message must reference the allowed prefix (lifecycle_root) and/or the offending path.
    assert str(root) in msg or "lifecycle" in msg


def test_module_api_accepts_path_under_matching_feature(lifecycle_layout: dict) -> None:
    """Req 9b auto-trigger: feature='foo' accepted when path is under lifecycle/foo/."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    resolved = validate_artifact_path(str(good), str(root), feature="foo")
    assert resolved == str(good.resolve())


def test_module_api_rejects_path_under_mismatched_feature(lifecycle_layout: dict) -> None:
    """Req 9b auto-trigger: feature='bar' rejected when path is under lifecycle/foo/."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(good), str(root), feature="bar")
    msg = str(exc_info.value)
    assert "bar" in msg


def test_module_api_rejects_path_equal_to_lifecycle_root(lifecycle_layout: dict) -> None:
    """Req 9b strict prefix: candidate == lifecycle_root is rejected."""
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(root), str(root))
    msg = str(exc_info.value)
    assert "strictly under" in msg or str(root) in msg


def test_module_api_valid_path_returns_realpath(lifecycle_layout: dict) -> None:
    """Valid path under lifecycle/ returns its realpath (str)."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    resolved = validate_artifact_path(str(good), str(root))
    assert resolved == str(good.resolve())
    # The return is a string (not Path).
    assert isinstance(resolved, str)


def test_module_api_prepare_dispatch_returns_sha_and_path(lifecycle_layout: dict) -> None:
    """``prepare_dispatch`` fuses validation + SHA-256 in one call."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    result = prepare_dispatch(str(good), str(root), feature="foo")
    expected_sha = hashlib.sha256(good.read_bytes()).hexdigest()
    assert result == {
        "resolved_path": str(good.resolve()),
        "sha256": expected_sha,
    }


# ---------------------------------------------------------------------------
# (2) CLI subprocess tests
# ---------------------------------------------------------------------------


def _run_cli(lifecycle_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke ``python3 -m cortex_command.critical_review`` with --lifecycle-root."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.critical_review",
            "--lifecycle-root",
            str(lifecycle_root),
            *args,
        ],
        capture_output=True,
        text=True,
    )


def test_cli_rejects_symlink_nonzero_exit_and_stderr(lifecycle_layout: dict) -> None:
    """Req 9d end-to-end: CLI rejects a symlink path with non-zero exit + stderr message."""
    evil = lifecycle_layout["evil_symlink"]
    root = lifecycle_layout["lifecycle_root"]
    result = _run_cli(root, "prepare-dispatch", str(evil))
    assert result.returncode != 0, (
        f"Expected non-zero exit; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Stderr must carry the rejection diagnostic.
    assert (
        "symlink" in result.stderr.lower()
        or "path validation failed" in result.stderr.lower()
    ), f"Expected rejection message in stderr; got {result.stderr!r}"


def test_cli_accepts_valid_path_and_emits_json(lifecycle_layout: dict) -> None:
    """CLI returns exit 0 + JSON {resolved_path, sha256} for a valid path."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    result = _run_cli(root, "prepare-dispatch", str(good))
    assert result.returncode == 0, (
        f"Expected exit 0; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert "resolved_path" in payload
    assert "sha256" in payload
    assert payload["resolved_path"] == str(good.resolve())
    assert payload["sha256"] == hashlib.sha256(good.read_bytes()).hexdigest()
