"""Unit tests for the live status-view feature bucketing.

Covers the recoverable_branch discriminator: a built-but-merge-blocked
recoverable feature is surfaced in its own group rather than lumped into the
failed bucket, and non-recoverable features bucket exactly as before.
"""

from __future__ import annotations

import unittest

from cortex_command.overnight.state import OvernightFeatureStatus
from cortex_command.overnight.status import bucket_features


class TestBucketFeatures(unittest.TestCase):
    def test_recoverable_not_failed(self):
        """A deferred feature with recoverable_branch is recoverable, not failed."""
        features = {
            "feat-recoverable": OvernightFeatureStatus(
                status="deferred", recoverable_branch="pipeline/feat-recoverable"
            ),
        }
        buckets = bucket_features(features)
        self.assertNotIn("feat-recoverable", buckets.failed)
        self.assertIn("feat-recoverable", buckets.recoverable)

    def test_non_recoverable_buckets_unchanged(self):
        """Without recoverable_branch, every status buckets exactly as before."""
        features = {
            "feat-running": OvernightFeatureStatus(
                status="running", started_at="2026-01-01T00:00:00+00:00"
            ),
            "feat-pending": OvernightFeatureStatus(status="pending"),
            "feat-merged": OvernightFeatureStatus(status="merged"),
            "feat-failed": OvernightFeatureStatus(status="failed"),
            "feat-deferred": OvernightFeatureStatus(status="deferred"),
            "feat-paused": OvernightFeatureStatus(status="paused"),
        }
        buckets = bucket_features(features)
        self.assertEqual([n for n, _ in buckets.running], ["feat-running"])
        self.assertEqual(buckets.pending, ["feat-pending"])
        self.assertEqual(buckets.completed, ["feat-merged"])
        # failed/deferred/paused (without recoverable_branch) all land in failed.
        self.assertCountEqual(
            buckets.failed, ["feat-failed", "feat-deferred", "feat-paused"]
        )
        self.assertEqual(buckets.recoverable, [])


if __name__ == "__main__":
    unittest.main()
