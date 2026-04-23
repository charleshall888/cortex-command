"""Regression tests for repair-agent prompt template path resolution.

Ensures _REPAIR_TEMPLATE is an absolute path that resolves correctly
regardless of the process's current working directory.
"""

from __future__ import annotations

from cortex_command.pipeline.conflict import _REPAIR_TEMPLATE


def test_repair_template_path_is_cwd_independent(monkeypatch, tmp_path):
    """_REPAIR_TEMPLATE.exists() must return True even when CWD has no claude/ subtree."""
    monkeypatch.chdir(tmp_path)
    assert _REPAIR_TEMPLATE.exists(), (
        f"_REPAIR_TEMPLATE does not exist after chdir to {tmp_path}: {_REPAIR_TEMPLATE}"
    )
