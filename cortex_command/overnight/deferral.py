"""Question deferral system for overnight orchestration.

When the pipeline encounters a question that requires human input,
it defers the question to a markdown file in the deferred/ directory
rather than blocking the session. Questions are numbered sequentially
per feature: {feature}-q001.md, {feature}-q002.md, etc.

Severity levels:
    blocking: Feature cannot proceed without human decision. Feature paused.
    non-blocking: Worker made a reasonable default choice. Human should validate.
    informational: Something unexpected discovered. No action needed.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.common import durable_fsync


# Default directory for deferred question files
DEFAULT_DEFERRED_DIR = Path("deferred")


# Valid deferral severity levels
SEVERITY_BLOCKING = "blocking"
SEVERITY_NON_BLOCKING = "non-blocking"
SEVERITY_INFORMATIONAL = "informational"

SEVERITIES = (
    SEVERITY_BLOCKING,
    SEVERITY_NON_BLOCKING,
    SEVERITY_INFORMATIONAL,
)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeferralQuestion:
    """A single deferred question captured during overnight execution.

    Fields:
        feature: Name of the feature the worker was implementing.
        question_id: Numeric identifier for this question within the feature.
        severity: One of blocking, non-blocking, or informational.
        context: What the worker was doing when the ambiguity arose.
        question: The specific ambiguity or decision needed.
        options_considered: Alternatives the worker identified.
        pipeline_attempted: What the pipeline tried before deferring.
        default_choice: For non-blocking, what the system proceeded with.
            Optional; typically None for blocking and informational.
        created_at: ISO 8601 timestamp when the question was created.
    """

    feature: str
    question_id: int
    severity: str
    context: str
    question: str
    options_considered: list[str] = field(default_factory=list)
    pipeline_attempted: str = ""
    default_choice: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"Invalid severity {self.severity!r}; "
                f"must be one of {SEVERITIES}"
            )
        if not isinstance(self.question_id, int) or self.question_id < 0:
            raise ValueError(
                f"question_id must be a non-negative integer, "
                f"got {self.question_id!r}"
            )


def next_question_id(deferred_dir: Path, feature: str) -> int:
    """Return a hint for the next available question ID for a feature.

    Scans ``deferred_dir`` for files matching ``{feature}-q{NNN}.md`` and
    returns max(NNN) + 1.  Returns 1 when no matching files exist.

    This value is used as a starting-point hint to reduce retry loops;
    actual uniqueness is enforced by ``O_CREAT | O_EXCL`` in
    :func:`write_deferral`, which atomically claims the destination
    filename and retries on collision.
    """
    pattern = f"{feature}-q*.md"
    existing = list(deferred_dir.glob(pattern))

    id_re = re.compile(rf"^{re.escape(feature)}-q(\d+)\.md$")

    max_id = 0
    for path in existing:
        m = id_re.match(path.name)
        if m:
            max_id = max(max_id, int(m.group(1)))

    return max_id + 1


def _format_deferral_markdown(question: DeferralQuestion) -> str:
    """Format a DeferralQuestion as a structured markdown string.

    The "Default Choice" section is omitted entirely for blocking severity.
    """
    qid = question.question_id
    lines: list[str] = [
        f"# Deferred Question: {question.feature} #{qid:03d}",
        "",
        f"**Severity**: {question.severity}",
        f"**Created**: {question.created_at}",
        "",
        "## Context",
        question.context,
        "",
        "## Question",
        question.question,
        "",
        "## Options Considered",
    ]

    for option in question.options_considered:
        lines.append(f"- {option}")

    lines.append("")
    lines.append("## What the Pipeline Tried")
    lines.append(question.pipeline_attempted)

    if question.severity != SEVERITY_BLOCKING and question.default_choice is not None:
        lines.append("")
        lines.append("## Default Choice")
        lines.append(question.default_choice)

    lines.append("")  # trailing newline
    return "\n".join(lines)


def write_deferral(
    question: DeferralQuestion,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
    _max_attempts: int = 100,
) -> Path:
    """Write a DeferralQuestion as a structured markdown file.

    Creates ``deferred_dir`` if it does not exist.  If ``question.question_id``
    is 0 (the default for "not yet assigned"), the next sequential ID is
    determined via :func:`next_question_id` as a starting-point hint.

    Uses ``O_CREAT | O_EXCL`` to atomically claim the destination filename,
    retrying with incremented IDs on collision.  This eliminates the TOCTOU
    race inherent in a scan-then-write pattern.

    Args:
        question: The deferral question to persist.
        deferred_dir: Directory to write the markdown file into.
        _max_attempts: Maximum number of IDs to try before raising.

    Returns:
        Path to the written markdown file.
    """
    deferred_dir.mkdir(parents=True, exist_ok=True)

    # Use the scan as a starting-point hint (avoids unnecessary retries)
    if question.question_id == 0:
        candidate_id = next_question_id(deferred_dir, question.feature)
    else:
        candidate_id = question.question_id

    # O_EXCL loop: atomically claim the destination filename
    for attempt in range(_max_attempts):
        qid = candidate_id + attempt
        filename = f"{question.feature}-q{qid:03d}.md"
        dest = deferred_dir / filename

        try:
            fd = os.open(
                str(dest),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            continue

        # Successfully claimed the file — write content
        question.question_id = qid
        content = _format_deferral_markdown(question)
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(str(dest))
            except OSError:
                pass
            raise

        return dest

    raise OSError(
        f"Could not claim a deferral filename after {_max_attempts} attempts "
        f"for feature {question.feature!r}"
    )


def _parse_deferral_file(path: Path) -> DeferralQuestion:
    """Parse a single deferral markdown file into a DeferralQuestion.

    Raises ValueError if the file is malformed.
    """
    text = path.read_text(encoding="utf-8")

    # Extract feature and question_id from the title line
    title_match = re.search(
        r"^# Deferred Question:\s+(.+?)\s+#(\d+)\s*$", text, re.MULTILINE
    )
    if not title_match:
        raise ValueError(f"Missing or malformed title line in {path.name}")

    feature = title_match.group(1)
    question_id = int(title_match.group(2))

    # Extract severity
    severity_match = re.search(
        r"^\*\*Severity\*\*:\s*(.+?)\s*$", text, re.MULTILINE
    )
    if not severity_match:
        raise ValueError(f"Missing severity in {path.name}")
    severity = severity_match.group(1)

    # Extract created_at
    created_match = re.search(
        r"^\*\*Created\*\*:\s*(.+?)\s*$", text, re.MULTILINE
    )
    if not created_match:
        raise ValueError(f"Missing created timestamp in {path.name}")
    created_at = created_match.group(1)

    # Split into sections by ## headers
    sections: dict[str, str] = {}
    parts = re.split(r"^## (.+?)\s*$", text, flags=re.MULTILINE)
    # parts[0] is everything before the first ##, then alternating header/content
    for i in range(1, len(parts) - 1, 2):
        header = parts[i].strip()
        content = parts[i + 1].strip()
        sections[header] = content

    # Extract required sections
    context = sections.get("Context")
    if context is None:
        raise ValueError(f"Missing ## Context section in {path.name}")

    question = sections.get("Question")
    if question is None:
        raise ValueError(f"Missing ## Question section in {path.name}")

    # Extract options_considered as bullet list items
    options_text = sections.get("Options Considered", "")
    options_considered = [
        line[2:].strip()
        for line in options_text.splitlines()
        if line.strip().startswith("- ")
    ]

    # Extract pipeline_attempted
    pipeline_attempted = sections.get("What the Pipeline Tried", "") or sections.get("What the Lead Tried", "")

    # Extract default_choice (may be absent for blocking questions)
    default_choice = sections.get("Default Choice")

    return DeferralQuestion(
        feature=feature,
        question_id=question_id,
        severity=severity,
        context=context,
        question=question,
        options_considered=options_considered,
        pipeline_attempted=pipeline_attempted,
        default_choice=default_choice,
        created_at=created_at,
    )


def read_deferrals(
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> list[DeferralQuestion]:
    """Read all deferral files from a directory and return parsed questions.

    Scans ``deferred_dir`` for ``*-q*.md`` files, parses each into a
    ``DeferralQuestion``, and returns them sorted by (feature, question_id).

    Malformed files are skipped with a warning to stderr.
    """
    if not deferred_dir.is_dir():
        return []

    results: list[DeferralQuestion] = []
    for path in sorted(deferred_dir.glob("*-q*.md")):
        try:
            dq = _parse_deferral_file(path)
            results.append(dq)
        except (ValueError, OSError) as exc:
            warnings.warn(
                f"Skipping malformed deferral file {path.name}: {exc}",
                stacklevel=2,
            )

    results.sort(key=lambda dq: (dq.feature, dq.question_id))
    return results


def read_deferrals_for_feature(
    feature: str,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> list[DeferralQuestion]:
    """Read deferral files for a specific feature.

    Convenience wrapper around ``read_deferrals()`` that filters to
    questions matching the given *feature* name.
    """
    return [
        dq
        for dq in read_deferrals(deferred_dir)
        if dq.feature == feature
    ]


@dataclass
class EscalationEntry:
    """A single escalation entry raised by a worker during overnight execution.

    Written to ``lifecycle/escalations.jsonl`` as a JSONL append log.
    The escalation_id format is ``{feature}-{round}-q{N}`` where N is
    determined by counting existing escalation entries for the same
    feature+round.

    Fields:
        escalation_id: Unique identifier for this escalation.
        feature: Name of the feature the worker was implementing.
        round: The orchestration round number.
        question: The specific question requiring human input.
        context: What the worker was doing when the question arose.
        ts: ISO 8601 timestamp when the escalation was created.
    """

    escalation_id: str
    feature: str
    round: int
    question: str
    context: str
    ts: str = field(default_factory=_now_iso)


def write_escalation(
    entry: EscalationEntry,
    escalations_path: Path = Path("lifecycle/escalations.jsonl"),
) -> None:
    """Append an escalation entry to the JSONL escalation log.

    Creates the parent directory and file if they do not exist.
    Each line is a JSON object with ``type: "escalation"`` plus the
    entry's fields.

    Args:
        entry: The escalation entry to persist.
        escalations_path: Path to the JSONL file.
    """
    escalations_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "type": "escalation",
        "escalation_id": entry.escalation_id,
        "feature": entry.feature,
        "round": entry.round,
        "question": entry.question,
        "context": entry.context,
        "ts": entry.ts,
    }

    with open(escalations_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        durable_fsync(f.fileno())


def _next_escalation_n(
    feature: str,
    round: int,
    escalations_path: Path,
) -> int:
    """Return the next sequential N for an escalation_id.

    Counts existing ``"escalation"`` type entries in *escalations_path*
    that match *feature* and *round*, then returns count + 1.

    TOCTOU note: there is a theoretical race between reading the count
    here and appending the new entry in ``write_escalation`` — a
    concurrent caller with the same feature+round could read the same
    count and produce a duplicate escalation_id.  This is safe under the
    current architecture because the overnight orchestrator dispatches at
    most one coroutine per feature, so the same feature+round pair is
    never processed concurrently.  The JSONL append pattern also makes
    ``O_EXCL``-style atomic creation inapplicable (we append lines, not
    create unique files).  If the dispatch model ever changes to allow
    concurrent workers on the same feature+round, this function will
    need a locking mechanism or an atomic counter.
    """
    count = 0
    if escalations_path.is_file():
        with open(escalations_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    obj.get("type") == "escalation"
                    and obj.get("feature") == feature
                    and obj.get("round") == round
                ):
                    count += 1
    return count + 1


def summarize_deferrals(questions: list[DeferralQuestion]) -> str:
    """Produce a summary string of deferred questions grouped by severity and feature.

    Format::

        3 deferred questions (1 blocking, 2 non-blocking):
        - feature-a: 2 questions (1 blocking, 1 non-blocking)
        - feature-b: 1 question (informational)

    Args:
        questions: List of deferred questions to summarize.

    Returns:
        Human-readable summary string. Empty string if no questions.
    """
    if not questions:
        return "No deferred questions."

    # Count by severity
    sev_counts: dict[str, int] = {}
    for q in questions:
        sev_counts[q.severity] = sev_counts.get(q.severity, 0) + 1

    # Count by feature and severity
    feature_sev: dict[str, dict[str, int]] = {}
    for q in questions:
        if q.feature not in feature_sev:
            feature_sev[q.feature] = {}
        feature_sev[q.feature][q.severity] = feature_sev[q.feature].get(q.severity, 0) + 1

    # Build top-level summary
    total = len(questions)
    sev_parts = []
    for sev in SEVERITIES:
        count = sev_counts.get(sev, 0)
        if count:
            sev_parts.append(f"{count} {sev}")

    lines = [f"{total} deferred question{'s' if total != 1 else ''} ({', '.join(sev_parts)}):"]

    # Per-feature breakdown
    for feature in sorted(feature_sev):
        counts = feature_sev[feature]
        feat_total = sum(counts.values())
        feat_parts = []
        for sev in SEVERITIES:
            count = counts.get(sev, 0)
            if count:
                feat_parts.append(f"{count} {sev}")
        q_word = "question" if feat_total == 1 else "questions"
        lines.append(f"- {feature}: {feat_total} {q_word} ({', '.join(feat_parts)})")

    return "\n".join(lines)
