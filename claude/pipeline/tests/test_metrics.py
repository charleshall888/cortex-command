"""Tests for claude/pipeline/metrics.py.

Covers: discover_pipeline_event_logs
"""

from __future__ import annotations

import unittest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
PIPELINE_LOGS_FIXTURE = FIXTURES_DIR / "pipeline_logs"


class TestDiscoverPipelineEventLogs(unittest.TestCase):
    """Tests for discover_pipeline_event_logs."""

    def _fn(self, lifecycle_dir: Path):
        from claude.pipeline.metrics import discover_pipeline_event_logs
        return discover_pipeline_event_logs(lifecycle_dir)

    def test_pipeline_events_sources(self):
        """Returns all three pipeline-events.log paths in sorted order."""
        result = self._fn(PIPELINE_LOGS_FIXTURE)

        expected = sorted([
            PIPELINE_LOGS_FIXTURE / "pipeline-events.log",
            PIPELINE_LOGS_FIXTURE / "sessions" / "s1" / "pipeline-events.log",
            PIPELINE_LOGS_FIXTURE / "sessions" / "s2" / "pipeline-events.log",
        ])

        self.assertEqual(result, expected)

    def test_empty_dir_returns_empty_list(self, tmp_path=None):
        """Returns [] when no pipeline-events.log files exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._fn(Path(tmpdir))
            self.assertEqual(result, [])

    def test_nonexistent_dir_returns_empty_list(self):
        """Returns [] when the directory does not exist."""
        result = self._fn(Path("/nonexistent/path/that/does/not/exist"))
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
