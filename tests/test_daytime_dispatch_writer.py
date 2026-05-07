"""Tests for ``cortex_command.overnight.daytime_dispatch_writer``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cortex_command.overnight.daytime_dispatch_writer import main


@pytest.fixture
def feature_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set CWD to tmp_path and create lifecycle/{feature}/ subdir."""
    monkeypatch.chdir(tmp_path)
    feature = "test-feature"
    (tmp_path / "lifecycle" / feature).mkdir(parents=True)
    return tmp_path / "lifecycle" / feature


def test_init_writes_fresh_dispatch_json(feature_dir: Path) -> None:
    rc = main([
        "--feature", "test-feature",
        "--mode", "init",
        "--dispatch-id", "deadbeefdeadbeefdeadbeefdeadbeef",
    ])
    assert rc == 0
    payload = json.loads((feature_dir / "daytime-dispatch.json").read_text())
    assert payload["schema_version"] == 1
    assert payload["dispatch_id"] == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert payload["feature"] == "test-feature"
    assert payload["pid"] is None
    assert "start_ts" in payload
    assert payload["start_ts"].endswith("Z")


def test_update_pid_mutates_only_pid(feature_dir: Path) -> None:
    main([
        "--feature", "test-feature",
        "--mode", "init",
        "--dispatch-id", "feedfacefeedfacefeedfacefeedface",
    ])
    before = json.loads((feature_dir / "daytime-dispatch.json").read_text())

    rc = main([
        "--feature", "test-feature",
        "--mode", "update-pid",
        "--pid", "12345",
    ])
    assert rc == 0
    after = json.loads((feature_dir / "daytime-dispatch.json").read_text())
    assert after["pid"] == 12345
    assert after["dispatch_id"] == before["dispatch_id"]
    assert after["feature"] == before["feature"]
    assert after["schema_version"] == before["schema_version"]
    assert after["start_ts"] == before["start_ts"]


def test_atomic_write_leaves_no_tmp_artifacts(feature_dir: Path) -> None:
    main([
        "--feature", "test-feature",
        "--mode", "init",
        "--dispatch-id", "0123456789abcdef0123456789abcdef",
    ])
    leftover_tmps = list(feature_dir.glob(".daytime-dispatch-*.tmp"))
    assert leftover_tmps == [], f"tmp files leaked: {leftover_tmps}"


def test_update_pid_against_missing_dispatch_raises(feature_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        main([
            "--feature", "test-feature",
            "--mode", "update-pid",
            "--pid", "99",
        ])
