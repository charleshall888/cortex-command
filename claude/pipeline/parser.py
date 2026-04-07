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
    """Parsed representation of lifecycle/master-plan.md."""

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
    """Parsed representation of lifecycle/{feature}/plan.md."""

    feature: str
    overview: str
    tasks: list[FeatureTask] = field(default_factory=list)


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
        path: Path to the lifecycle/{feature}/plan.md file.

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
    tasks = _parse_tasks(text, path)

    return FeaturePlan(feature=feature_name, overview=overview, tasks=tasks)


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


def _parse_tasks(text: str, path: Path) -> list[FeatureTask]:
    """Parse all ### Task N: sections from a feature plan."""
    tasks: list[FeatureTask] = []

    # Normalize separator variants (em dash, en dash, hyphen) to colon
    text = _normalize_task_separators(text)

    # Find all task headings: ### Task N: description
    # Relaxed regex also accepts em dash, en dash, and hyphen as belt-and-suspenders
    task_pattern = re.compile(
        r"^###\s+Task\s+(\d+)\s*[:\u2014\u2013-]\s*(.+)$", re.MULTILINE
    )
    matches = list(task_pattern.finditer(text))

    if not matches:
        raise ValueError(f"Feature plan at {path} has no task sections")

    for i, match in enumerate(matches):
        task_num = int(match.group(1))
        description = match.group(2).strip()

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
        complexity = _parse_field_string(task_body, "Complexity") or "simple"
        status = _parse_field_status(task_body)

        tasks.append(FeatureTask(
            number=task_num,
            description=description,
            files=files,
            depends_on=depends_on,
            complexity=complexity,
            status=status,
        ))

    return tasks


def _parse_field_files(body: str) -> list[str]:
    """Extract the Files field value as a list of file paths."""
    match = re.search(
        r"[-*]\s+\*\*Files\*\*:\s*(.+?)(?:\n[-*]\s+\*\*|\n###|\n##|\Z)",
        body, re.DOTALL
    )
    if not match:
        return []

    raw = match.group(1).strip()
    if not raw or raw.lower() == "none":
        return []

    # Files may be comma-separated or on separate lines
    # Handle both: "path/a, path/b" and multi-line with backticks
    # Strip backticks and split on commas or newlines
    raw = raw.replace("`", "")
    parts = re.split(r"[,\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _parse_field_depends_on(
    body: str, task_num: int, path: Path
) -> list[int]:
    """Extract the Depends on field as a list of task numbers."""
    match = re.search(
        r"[-*]\s+\*\*Depends\s+on\*\*:\s*(.+)", body
    )
    if not match:
        return []

    raw = match.group(1).strip()
    if raw.lower() == "none":
        return []

    # Parse formats: [1, 3], [1], 1, 3, or just numbers
    numbers = re.findall(r"\d+", raw)
    if not numbers and raw.lower() != "none":
        raise ValueError(
            f"Task {task_num} in {path}: cannot parse 'Depends on' value: {raw!r}"
        )

    return [int(n) for n in numbers]


def _parse_field_string(body: str, field_name: str) -> Optional[str]:
    """Extract a simple string field value (e.g., Complexity)."""
    pattern = rf"[-*]\s+\*\*{re.escape(field_name)}\*\*:\s*(.+)"
    match = re.search(pattern, body)
    if not match:
        return None
    return match.group(1).strip()


def _parse_field_status(body: str) -> str:
    """Extract the Status field and return 'pending' or 'done'."""
    match = re.search(
        r"[-*]\s+\*\*Status\*\*:\s*(.+)", body
    )
    if not match:
        return "pending"

    raw = match.group(1).strip()
    if re.search(r"\[x\]", raw, re.IGNORECASE):
        return "done"
    return "pending"
