"""Plan parsers for master plan and per-feature plan.md files.

Converts markdown planning artifacts into structured Python dataclasses
that the orchestrator loop uses for dispatch decisions. Uses only stdlib
(re, pathlib, dataclasses).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# The accepted per-task complexity vocabulary. A present-but-out-of-vocabulary
# value is normalized to ``complex`` (safe over-provision) at the parser
# boundary; an absent field keeps the ``simple`` default.
VALID_COMPLEXITIES = frozenset({"trivial", "simple", "complex"})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MasterPlanFeature:
    """A single feature row from the master plan's Features table."""

    priority: int
    name: str
    complexity: str
    task_count: int
    summary: str


@dataclass
class MasterPlanConfig:
    """Configuration section of the master plan."""

    test_command: Optional[str] = None
    base_branch: str = "main"


@dataclass
class MasterPlan:
    """Parsed representation of cortex/lifecycle/master-plan.md."""

    name: str
    features: list[MasterPlanFeature] = field(default_factory=list)
    config: MasterPlanConfig = field(default_factory=MasterPlanConfig)


@dataclass
class FeatureTask:
    """A single task from a feature plan."""

    number: int
    description: str
    files: list[str] = field(default_factory=list)
    depends_on: list[int] = field(default_factory=list)
    complexity: str = "simple"
    status: str = "pending"


@dataclass
class FeaturePlan:
    """Parsed representation of cortex/lifecycle/{feature}/plan.md."""

    feature: str
    overview: str
    tasks: list[FeatureTask] = field(default_factory=list)
    # Records each present-but-out-of-vocabulary complexity that was coerced to
    # ``complex`` at the parser boundary. Each entry is
    # ``{"task": <task-number>, "original": <oov-string>}``. The parser itself
    # does no logging; the caller (which holds the session-events-log handle)
    # reads this to emit a report-visible normalization event.
    normalized_complexities: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Master plan parser
# ---------------------------------------------------------------------------

def parse_master_plan(path: Path) -> MasterPlan:
    """Parse a master plan markdown file into structured data.

    Args:
        path: Path to the master-plan.md file.

    Returns:
        A MasterPlan dataclass with features and configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is malformed (missing sections, bad fields).
    """
    text = path.read_text(encoding="utf-8")

    # -- Parse pipeline name from the H1 heading --
    name_match = re.search(r"^#\s+Master\s+Plan:\s*(.+)$", text, re.MULTILINE)
    if not name_match:
        raise ValueError(
            f"Master plan at {path} is missing the '# Master Plan: <name>' heading"
        )
    pipeline_name = name_match.group(1).strip()

    # -- Locate sections by H2 headings --
    features_text = _extract_section(text, "Features")
    config_text = _extract_section(text, "Configuration")

    if features_text is None:
        raise ValueError(
            f"Master plan at {path} is missing the '## Features' section"
        )

    # -- Parse features table --
    features = _parse_features_table(features_text, path)

    # -- Parse configuration table --
    config = _parse_config_table(config_text, path) if config_text else MasterPlanConfig()

    return MasterPlan(name=pipeline_name, features=features, config=config)


def _extract_section(text: str, heading: str) -> Optional[str]:
    """Extract the body text under a ## heading, up to the next ## or EOF."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None

    start = match.end()
    # Find the next H2 heading or end of string
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def _parse_features_table(section: str, path: Path) -> list[MasterPlanFeature]:
    """Parse the pipe-delimited Features table rows."""
    features: list[MasterPlanFeature] = []

    # Find table rows: lines starting and ending with |
    table_lines = [
        line.strip() for line in section.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]

    if len(table_lines) < 2:
        raise ValueError(
            f"Features table in {path} must have at least a header row and separator"
        )

    # Skip header row (index 0) and separator row (index 1)
    data_rows = table_lines[2:]

    if not data_rows:
        raise ValueError(f"Features table in {path} has no data rows")

    for i, row in enumerate(data_rows, start=1):
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 5:
            raise ValueError(
                f"Features table row {i} in {path} has {len(cells)} columns, "
                f"expected 5: {row}"
            )

        priority_str, name, complexity, tasks_str, summary = (
            cells[0].strip(),
            cells[1].strip(),
            cells[2].strip(),
            cells[3].strip(),
            cells[4].strip(),
        )

        try:
            priority = int(priority_str)
        except ValueError:
            raise ValueError(
                f"Features table row {i} in {path}: "
                f"priority must be an integer, got {priority_str!r}"
            )

        try:
            task_count = int(tasks_str)
        except ValueError:
            raise ValueError(
                f"Features table row {i} in {path}: "
                f"task count must be an integer, got {tasks_str!r}"
            )

        if not name:
            raise ValueError(
                f"Features table row {i} in {path}: feature name is empty"
            )

        features.append(MasterPlanFeature(
            priority=priority,
            name=name,
            complexity=complexity,
            task_count=task_count,
            summary=summary,
        ))

    return features


def _parse_config_table(section: str, path: Path) -> MasterPlanConfig:
    """Parse the pipe-delimited Configuration table into a MasterPlanConfig."""
    config = MasterPlanConfig()

    # Find table rows
    table_lines = [
        line.strip() for line in section.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]

    if len(table_lines) < 2:
        # No table found; return defaults
        return config

    # Skip header and separator
    data_rows = table_lines[2:]

    for row in data_rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 2:
            continue

        key = cells[0].strip()
        value = cells[1].strip()

        if key == "test_command":
            config.test_command = None if value.lower() == "none" else value
        elif key == "base_branch":
            config.base_branch = value

    return config


# ---------------------------------------------------------------------------
# Feature plan parser
# ---------------------------------------------------------------------------

def parse_feature_plan(path: Path) -> FeaturePlan:
    """Parse a feature plan markdown file into structured data.

    Args:
        path: Path to the cortex/lifecycle/{feature}/plan.md file.

    Returns:
        A FeaturePlan dataclass with feature name, overview, and tasks.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is malformed (missing heading, bad task format).
    """
    text = path.read_text(encoding="utf-8")

    # -- Parse feature name from the H1 heading --
    name_match = re.search(r"^#\s+Plan:\s*(.+)$", text, re.MULTILINE)
    if not name_match:
        raise ValueError(
            f"Feature plan at {path} is missing the '# Plan: <name>' heading"
        )
    feature_name = name_match.group(1).strip()

    # -- Parse overview --
    overview_text = _extract_section(text, "Overview")
    overview = overview_text.strip() if overview_text else ""

    # -- Parse tasks --
    tasks, normalized_complexities = _parse_tasks(text, path)

    return FeaturePlan(
        feature=feature_name,
        overview=overview,
        tasks=tasks,
        normalized_complexities=normalized_complexities,
    )


def _normalize_task_separators(text: str) -> str:
    """Substitute accepted separator variants with colon on task heading lines.

    Accepts em dash (U+2014), en dash (U+2013), and hyphen-minus (U+002D) as
    separators between the task number and description, normalizing them to a
    colon so the downstream regex can match consistently.
    """
    return re.sub(
        r"^(###\s+Task\s+\d+)\s*[—–-]\s*",
        r"\1: ",
        text,
        flags=re.MULTILINE,
    )


def _parse_tasks(text: str, path: Path) -> tuple[list[FeatureTask], list[dict]]:
    """Parse all ### Task N: sections from a feature plan.

    Returns the parsed tasks plus a list of out-of-vocabulary complexity
    normalizations (``{"task": <number>, "original": <oov-string>}``) so the
    caller can surface each coercion as a report-visible event.
    """
    tasks: list[FeatureTask] = []
    normalized_complexities: list[dict] = []

    # Normalize separator variants (em dash, en dash, hyphen) to colon
    text = _normalize_task_separators(text)

    # Find all task headings: ### Task N: description
    # Relaxed regex also accepts em dash, en dash, and hyphen as belt-and-suspenders
    task_pattern = re.compile(
        r"^###\s+Task\s+(\d+)\s*[:\u2014\u2013-]\s*(.+)$", re.MULTILINE
    )
    matches = list(task_pattern.finditer(text))

    # Letter-suffixed sub-task headings like ``### Task 3a:`` are not captured
    # by the integer-only ``task_pattern`` above; their bodies would be
    # silently absorbed into the preceding integer task, dropping the
    # sub-task's Files/Depends-on metadata from dispatch ordering. Fail loud
    # rather than silently mis-parse — the same posture #293 took for the
    # field parsers. Recognizing 3a/3b as first-class ordered units is a
    # deferred data-model change (FeatureTask.number is an int and
    # compute_dependency_batches keys on it); until then a letter-suffixed
    # task heading is unrecoverable drift.
    subtask = re.compile(r"^###\s+Task\s+\d+[A-Za-z]", re.MULTILINE).search(text)
    if subtask is not None:
        offending = subtask.group(0).strip()
        raise ValueError(
            f"Feature plan at {path} uses an unsupported sub-task heading "
            f"({offending!r}); letter-suffixed task numbers (### Task Na) are "
            f"not yet parseable and would silently drop the sub-task from "
            f"dispatch ordering. Use integer task numbers."
        )

    if not matches:
        raise ValueError(f"Feature plan at {path} has no task sections")

    for i, match in enumerate(matches):
        task_num = int(match.group(1))
        description = match.group(2).strip()
        description = re.sub(r'\s*\[[xX]\]\s*$', '', description).strip()

        # Extract the body of this task section (up to next ### or ## or EOF)
        start = match.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            # Find next ## heading or end of string
            next_h2 = re.search(r"^##\s+", text[start:], re.MULTILINE)
            end = start + next_h2.start() if next_h2 else len(text)

        task_body = text[start:end]

        files = _parse_field_files(task_body)
        depends_on = _parse_field_depends_on(task_body, task_num, path)
        # An absent Complexity field keeps the ``simple`` default; only a
        # present-but-out-of-vocabulary value normalizes to ``complex``
        # (safe over-provision) and is recorded for the caller to surface.
        complexity = _parse_field_string(task_body, "Complexity") or "simple"
        if complexity not in VALID_COMPLEXITIES:
            normalized_complexities.append(
                {"task": task_num, "original": complexity}
            )
            complexity = "complex"
        status = _parse_field_status(task_body)

        tasks.append(FeatureTask(
            number=task_num,
            description=description,
            files=files,
            depends_on=depends_on,
            complexity=complexity,
            status=status,
        ))

    return tasks, normalized_complexities


# ---------------------------------------------------------------------------
# Per-task field parsers
# ---------------------------------------------------------------------------
#
# The known-safe dialect family (R1): every per-task field may appear with an
# optional leading bullet (``-``/``*``) and the colon either inside the bold
# (``**Files:**``) or outside it (``**Files**:``). The canonical form
# (``- **Files**:``) is one member of this family. Recovery is silent (the
# parser does no logging); only genuinely-unrecoverable drift raises ValueError
# so a malformed plan fails exactly one feature loudly rather than collapsing
# its dependency ordering silently.


def _field_match_shape(label: str) -> str:
    """Return the relaxed bullet/colon match shape for a bold field label.

    Accepts an optional leading bullet and the colon inside *or* outside the
    bold, i.e. all of ``**Files**:`` / ``**Files:**`` / ``- **Files**:`` /
    ``- **Files:**``. The whitespace inside the label tolerates the
    ``Depends on`` two-word form via the caller's ``\\s+`` between words.
    """
    return (
        r"(?:[-*]\s+)?"          # optional leading bullet
        r"(?:"
        rf"\*\*\s*{label}\s*:\s*\*\*"   # colon inside the bold
        r"|"
        rf"\*\*\s*{label}\s*\*\*\s*:"   # colon outside the bold
        r")"
    )


def _field_label_present(body: str, label: str) -> bool:
    """Return True iff ``label`` appears as a line-leading field bullet.

    A field label is a bold token (``**Files**``/``**Files:**``) immediately
    colon-adjacent, anchored at start-of-line (under ``re.MULTILINE``) with at
    most an optional ``[-*]\\s+`` bullet prefix — NOT arbitrary leading
    indentation. The start-of-line anchor (no indentation) is what excludes a
    nested Context sub-bullet (``  - **Depends on**: see Task 1``) and the
    colon-adjacency requirement excludes a colon-free prose mention
    (``- **Files** are frozen per Task 1``).
    """
    pattern = r"^" + _field_match_shape(label)
    return re.search(pattern, body, re.MULTILINE) is not None


def _parse_field_files(body: str) -> list[str]:
    """Extract the Files field value as a list of file paths.

    Preserves the multi-line (``re.DOTALL``) capture so the multi-line Files
    dialect (``- **Files**:`` at EOL followed by nested ``  - path`` bullets)
    parses to its path list. Raises ValueError when a line-leading colon-
    adjacent ``Files`` label is present but the captured value is empty
    (R2: fail-loud rather than silently dropping to ``[]``).
    """
    match = re.search(
        r"^" + _field_match_shape("Files")
        + r"[^\S\n]*(.*?)(?=\n(?:[-*]\s+)?\*\*|\n###|\n##|\Z)",
        body, re.DOTALL | re.MULTILINE
    )
    raw = match.group(1).strip() if match else ""

    if not raw:
        # An empty captured value with a present field label is unrecoverable
        # drift (R2): the label promised a value and none was extractable.
        if _field_label_present(body, "Files"):
            raise ValueError(
                "'Files' field label present but no usable value extracted"
            )
        return []

    if raw.lower() == "none":
        return []

    # Files may be comma-separated or on separate lines (the multi-line dialect
    # nests ``  - path`` bullets). Strip backticks, split on commas/newlines,
    # and strip any leading nested-bullet marker from each part.
    raw = raw.replace("`", "")
    parts = re.split(r"[,\n]+", raw)
    cleaned = [re.sub(r"^[-*]\s+", "", p.strip()).strip() for p in parts]
    return [p for p in cleaned if p]


# A list-conformant Depends-on value, after annotations are stripped: ``none``
# or a comma-separated sequence of task identifiers, each either bracketed
# (``[1]``, ``[1, 2]``) or bare. A task identifier is a digit run with an
# optional trailing letter-suffix (``3a``, ``13b``) — the live corpus's
# sub-task decomposition dialect. This accepts every canonical-template form
# (``[N]``, ``[N, M]``, ``N``, ``N, M``) plus the corpus's multi-bracket
# (``[1], [4]``) and sub-task (``[1, 3a, 3b]``) forms. Free prose that merely
# contains an incidental digit does not match and raises (R4).
_DEPENDS_ON_TASK_ID = r"\d+[a-z]?"
_DEPENDS_ON_ITEM = (
    rf"(?:\[\s*{_DEPENDS_ON_TASK_ID}(?:\s*,\s*{_DEPENDS_ON_TASK_ID})*\s*\]"
    rf"|{_DEPENDS_ON_TASK_ID})"
)
_DEPENDS_ON_LIST_CONFORMANT = re.compile(
    rf"^(?:none|{_DEPENDS_ON_ITEM}(?:\s*,\s*{_DEPENDS_ON_ITEM})*)$",
    re.IGNORECASE,
)

# A trailing free-text annotation the corpus appends after a complete list,
# delimited by an em dash, en dash, or spaced double-hyphen (``[1, 8] — note``).
# Stripped before the conformance check; not a single hyphen, which appears
# inside ordinary hyphenated prose.
_DEPENDS_ON_TRAILING_ANNOTATION = re.compile(r"\s+(?:[—–]|--)\s.*$")


def _parse_field_depends_on(
    body: str, task_num: int, path: Path
) -> list[int]:
    """Extract the Depends on field as a list of task numbers.

    Tolerates the live corpus's annotation dialects — parenthetical
    (``[1] (console-script must exist), [4] (...)``) and trailing em-dash notes
    (``[1, 8] — all live references must be removed``) — by stripping them
    before checking list-conformance (R4). Extracts dependency numbers only
    from the stripped, list-conformant remainder — so
    ``none (parallel-eligible with Task 1)`` resolves to ``[]`` rather than the
    phantom ``[1]`` the prior digit-scrape produced. A present label whose
    value is empty or non-list-conformant prose raises (R2/R4).
    """
    match = re.search(
        r"^" + _field_match_shape("Depends\\s+on") + r"\s*(.+)",
        body, re.MULTILINE
    )
    if not match:
        if _field_label_present(body, "Depends\\s+on"):
            raise ValueError(
                f"Task {task_num} in {path}: 'Depends on' field label present "
                f"but no usable value extracted"
            )
        return []

    raw = match.group(1).strip()

    if not raw:
        raise ValueError(
            f"Task {task_num} in {path}: 'Depends on' field label present "
            f"but no usable value extracted"
        )

    # Strip the corpus's annotation spans — parenthetical ``(...)`` anywhere and
    # a trailing em/en-dash free-text note — then require the remainder to be
    # list-conformant before extracting task numbers.
    stripped = re.sub(r"\([^)]*\)", "", raw)
    stripped = _DEPENDS_ON_TRAILING_ANNOTATION.sub("", stripped)
    stripped = stripped.strip().rstrip(".").strip()

    if not _DEPENDS_ON_LIST_CONFORMANT.match(stripped):
        raise ValueError(
            f"Task {task_num} in {path}: 'Depends on' value is not "
            f"list-conformant: {raw!r}"
        )

    if stripped.lower() == "none":
        return []

    # Extract the integer portion of each task identifier. A letter-suffixed
    # sub-task id (``3a``) collapses to its integer (``3``) here because
    # ``depends_on`` is ``list[int]`` — the same integer the pre-existing
    # digit-scrape produced; faithful sub-task ordering is out of this parser's
    # scope (the ``### Task Na`` heading itself is not recognized upstream).
    numbers = re.findall(r"\d+", stripped)
    if not numbers:
        raise ValueError(
            f"Task {task_num} in {path}: cannot parse 'Depends on' value: {raw!r}"
        )

    return [int(n) for n in numbers]


def _parse_field_string(body: str, field_name: str) -> Optional[str]:
    """Extract a simple string field value (e.g., Complexity)."""
    pattern = r"^" + _field_match_shape(re.escape(field_name)) + r"\s*(.+)"
    match = re.search(pattern, body, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _parse_field_status(body: str) -> str:
    """Extract the Status field and return 'pending' or 'done'.

    A missing Status legitimately defaults to ``pending`` — Status is NOT
    fail-loud (R2 applies only to Files/Depends-on). The relaxed dialect shape
    (R1) lets ``**Status:** [x]`` / no-bullet ``**Status**: [x]`` survive.
    """
    match = re.search(
        r"^" + _field_match_shape("Status") + r"\s*(.+)",
        body, re.MULTILINE
    )
    if not match:
        return "pending"

    raw = match.group(1).strip()
    if re.match(r"\[[xX]\]", raw):
        return "done"
    return "pending"
