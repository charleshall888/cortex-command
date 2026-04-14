"""Reference FeatureResult instances, one per status variant.

Tests may import these for fixture reuse rather than constructing inline.
"""

from claude.overnight.batch_runner import FeatureResult

COMPLETED = FeatureResult(name="feature-completed", status="completed")
FAILED = FeatureResult(name="feature-failed", status="failed", error="task failed")
PAUSED = FeatureResult(name="feature-paused", status="paused", error="paused for review")
DEFERRED = FeatureResult(name="feature-deferred", status="deferred", deferred_question_count=1)
REPAIR_COMPLETED = FeatureResult(name="feature-repair-completed", status="repair_completed")
