"""Unit tests for generate_batch_plan() path validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.overnight.batch_plan import generate_batch_plan


def test_relative_output_path_raises_value_error():
    """generate_batch_plan() rejects a relative output_path with ValueError."""
    with pytest.raises(ValueError, match="absolute"):
        generate_batch_plan(
            features=[],
            test_command=None,
            output_path=Path("relative/path"),
        )
