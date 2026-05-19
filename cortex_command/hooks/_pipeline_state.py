"""Pipeline-state detection for the scan-lifecycle hook.

Reads ``{lifecycle_dir}/overnight-state.json`` (when present) and
produces the ``pipeline_context`` summary string the bash hook emits at
lines 67-163 of ``hooks/cortex-scan-lifecycle.sh``. The Python port
replaces bash's ``jq``-with-``sed``-fallback dance with ``json.load`` +
``collections.Counter`` — there is no fallback path because ``json`` is
in the stdlib.

Behavior matrix (matches bash precedent):

* **No file / unreadable / missing ``phase``**: empty
  :class:`PipelineState` (no context string, Morning Review inactive).
* **``phase == "complete"`` AND all merged features have a
  ``feature_complete`` event in their ``events.log``**: empty
  :class:`PipelineState` — the overnight is dismissed.
* **``phase == "complete"`` AND at least one merged feature lacks a
  ``feature_complete`` event**: ``morning_review_active=True``,
  ``morning_review_features`` populated with every merged feature
  name, ``context_string = "☀️ Morning Review pending: N
  features"`` (where ``N`` is the merged-feature count, matching bash
  ``${#merged_features[@]}``).
* **Any other non-empty phase**: ``context_string = "Active pipeline:
  <phase> | Features: <total> total, <detail>"`` where ``<detail>``
  joins non-zero status counts in the bash detail order: ``merged,
  executing, reviewing, merging, paused, pending, failed``.

Task 5 does NOT modify ``scan_lifecycle.py``; Task 8 wires this
detector into the orchestrator.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# Bash precedent lines 156-167 enumerate the detail ordering explicitly
# in a fixed-order ``for pair in "merged:..." "executing:..." ...`` loop;
# tuple form is the authoritative wire order. Reproducing the bash
# ordering byte-for-byte is required so the golden-fixture replay
# (requirement #2 / Task 1 fixtures) matches under both topologies.
_DETAIL_STATUS_ORDER: tuple[str, ...] = (
    "merged",
    "executing",
    "reviewing",
    "merging",
    "paused",
    "pending",
    "failed",
)

# Bash lines 99 + 126: emoji + label exactly as the bash hook emits.
# The U+2600 + U+FE0F (variation-selector-16) sequence is the same
# byte sequence ``echo "☀️"`` produces in the bash hook source.
_MORNING_REVIEW_PREFIX = "☀️ Morning Review pending"


@dataclass(frozen=True)
class PipelineState:
    """Pipeline-state summary exposed to the orchestrator.

    Attributes
    ----------
    context_string:
        The ``pipeline_context`` line ready for inclusion in the
        SessionStart ``additionalContext`` payload. Empty string when
        no overnight is active or the overnight is dismissed.
    morning_review_active:
        ``True`` when the overnight is in the ``complete`` phase but
        at least one merged feature lacks a ``feature_complete``
        event in its ``events.log`` — the orchestrator uses this to
        emit the Morning Review banner and to suppress the same
        features from the "incomplete features" enumeration.
    morning_review_features:
        Set of merged-feature directory names to suppress from the
        incomplete-features list when Morning Review is active. Empty
        when ``morning_review_active`` is ``False``.
    """

    context_string: str = ""
    morning_review_active: bool = False
    morning_review_features: set[str] = field(default_factory=set)

    @classmethod
    def from_path(cls, state_file: Path | None) -> "PipelineState":
        """Build a :class:`PipelineState` from ``overnight-state.json``.

        Returns an empty state when ``state_file`` is ``None``, does
        not exist, is unreadable, fails to parse as JSON, or carries
        no ``phase`` field. Parsing failures are intentionally
        swallowed — the bash precedent silently degrades to empty
        context on jq failure (lines 91-92) and the Python port
        preserves that behavior so a malformed state file never
        breaks a SessionStart hook.

        The ``events.log`` lookup for the Morning Review dismissal
        check derives ``lifecycle_dir`` from ``state_file.parent`` —
        the bash hook hardcodes ``$LIFECYCLE_DIR/$fname/events.log``
        and the state file lives at ``$LIFECYCLE_DIR/
        overnight-state.json``, so the parent is the lifecycle root.
        """

        if state_file is None or not state_file.is_file():
            return cls()

        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()

        if not isinstance(data, dict):
            return cls()

        phase = data.get("phase")
        if not isinstance(phase, str) or not phase:
            return cls()

        features = data.get("features")
        if not isinstance(features, dict):
            features = {}

        lifecycle_dir = state_file.parent

        if phase == "complete":
            return cls._build_complete(features, lifecycle_dir)
        return cls._build_active(phase, features)

    @classmethod
    def _build_complete(
        cls, features: dict, lifecycle_dir: Path
    ) -> "PipelineState":
        """Handle the ``phase == "complete"`` branch.

        Mirrors bash lines 99-127: enumerate merged features, treat
        the overnight as dismissed iff every merged feature's
        ``events.log`` contains a ``"feature_complete"`` substring,
        otherwise activate Morning Review.
        """

        merged_features = [
            name
            for name, entry in features.items()
            if isinstance(entry, dict)
            and entry.get("status") == "merged"
        ]

        if not merged_features:
            # Bash: dismissed=true when array is empty (line 110-111).
            return cls()

        if all(
            cls._has_feature_complete_event(lifecycle_dir / name)
            for name in merged_features
        ):
            return cls()

        count = len(merged_features)
        return cls(
            context_string=f"{_MORNING_REVIEW_PREFIX}: {count} features",
            morning_review_active=True,
            morning_review_features=set(merged_features),
        )

    @classmethod
    def _build_active(
        cls, phase: str, features: dict
    ) -> "PipelineState":
        """Handle the non-``complete`` phase branch.

        Mirrors bash lines 128-170: ``total`` is the number of feature
        entries with a ``status`` field; per-status counts are derived
        from a :class:`collections.Counter`. Detail segments are
        emitted in the fixed bash order (:data:`_DETAIL_STATUS_ORDER`)
        and zero-count statuses are omitted.
        """

        statuses: list[str] = []
        for entry in features.values():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if isinstance(status, str):
                statuses.append(status)

        total = len(statuses)
        counter: Counter[str] = Counter(statuses)

        detail_parts = [
            f"{counter[name]} {name}"
            for name in _DETAIL_STATUS_ORDER
            if counter[name] > 0
        ]
        detail = ", ".join(detail_parts)

        return cls(
            context_string=(
                f"Active pipeline: {phase} | "
                f"Features: {total} total, {detail}"
            ),
            morning_review_active=False,
            morning_review_features=set(),
        )

    @staticmethod
    def _has_feature_complete_event(feature_dir: Path) -> bool:
        """Return ``True`` if ``feature_dir/events.log`` mentions ``feature_complete``.

        Bash precedent line 115 uses ``grep -q '"feature_complete"'``;
        the Python port matches that substring (with quotes) so the
        dismissal check fires on the same JSON-encoded event payloads
        the bash hook recognizes. An unreadable / missing
        ``events.log`` is treated as "no feature_complete event" —
        same as bash's ``2>/dev/null`` swallow + nonzero exit from
        grep, which keeps ``dismissed=false`` and triggers Morning
        Review.
        """

        events_log = feature_dir / "events.log"
        try:
            content = events_log.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return False
        return '"feature_complete"' in content
