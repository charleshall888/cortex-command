"""Review dispatch types and verdict parsing for overnight review gating.

Provides the ReviewResult dataclass for structured review outcomes and
parse_verdict() for extracting the JSON verdict block from review.md files
written by review agents.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReviewResult:
    """Structured result of a review dispatch cycle.

    Fields:
        approved: Whether the review verdict was APPROVED.
        deferred: Whether the feature was deferred (non-APPROVED after
            rework exhausted, or review failure).
        verdict: Raw verdict string (APPROVED, CHANGES_REQUESTED,
            REJECTED, or ERROR).
        cycle: Review cycle number (0 for errors, 1-2 for real reviews).
        issues: List of issue descriptions from the review agent.
    """

    approved: bool
    deferred: bool
    verdict: str
    cycle: int
    issues: list[str] = field(default_factory=list)


_ERROR_RESULT: dict = {"verdict": "ERROR", "cycle": 0, "issues": []}


def parse_verdict(review_path: Path) -> dict:
    """Extract the JSON verdict block from a review.md file.

    Reads the file at *review_path*, searches for a fenced JSON code block
    (````` ```json ... ``` `````) containing the verdict object, and returns
    the parsed dict.

    Args:
        review_path: Path to the review.md file (e.g.
            ``lifecycle/{feature}/review.md``).

    Returns:
        Parsed verdict dict with at least ``verdict``, ``cycle``, and
        ``issues`` keys.  Returns ``{"verdict": "ERROR", "cycle": 0,
        "issues": []}`` if the file does not exist or the JSON block is
        malformed.
    """
    try:
        content = review_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return dict(_ERROR_RESULT)

    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return dict(_ERROR_RESULT)

    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return dict(_ERROR_RESULT)
