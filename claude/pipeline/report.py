"""Summary reporting and notification for pipeline runs.

Generates a markdown completion report from pipeline state and triggers
the notification hook so the user knows the pipeline finished or needs
attention.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .state import FeatureStatus, PipelineState


def generate_report(state: PipelineState) -> str:
    """Produce a markdown summary of the pipeline run.

    Sections:
        - Header
        - Summary counts (total, completed, failed/paused)
        - Completed features list
        - Failed/paused features with reasons and retry counts
        - Retry summary per feature
        - Pipeline timing

    Args:
        state: The current (usually final) pipeline state.

    Returns:
        A markdown-formatted report string.
    """
    features = state.features
    total = len(features)

    completed = {n: fs for n, fs in features.items() if fs.status == "merged"}
    troubled = {
        n: fs
        for n, fs in features.items()
        if fs.status in ("failed", "paused")
    }

    lines: list[str] = []

    # Header
    lines.append("# Pipeline Report")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total features**: {total}")
    lines.append(f"- **Completed**: {len(completed)}")
    lines.append(f"- **Failed/Paused**: {len(troubled)}")
    lines.append(f"- **Pipeline phase**: {state.phase}")
    lines.append("")

    # Completed features
    lines.append("## Completed Features")
    lines.append("")
    if completed:
        for name in sorted(completed):
            lines.append(f"- {name}")
    else:
        lines.append("_None_")
    lines.append("")

    # Failed/paused features
    lines.append("## Failed/Paused Features")
    lines.append("")
    if troubled:
        for name in sorted(troubled):
            fs = troubled[name]
            reason = fs.last_error or "unknown"
            lines.append(f"- **{name}** ({fs.status}): {reason} (retries: {fs.retries})")
    else:
        lines.append("_None_")
    lines.append("")

    # Retry summary
    lines.append("## Retry Summary")
    lines.append("")
    has_retries = False
    for name in sorted(features):
        fs = features[name]
        if fs.retries > 0:
            lines.append(f"- {name}: {fs.retries}")
            has_retries = True
    if not has_retries:
        lines.append("_No retries_")
    lines.append("")

    # Timing
    lines.append("## Timing")
    lines.append("")
    lines.append(f"- **Started**: {state.started_at}")
    lines.append(f"- **Last updated**: {state.updated_at}")
    lines.append("")

    return "\n".join(lines)


def write_report(report: str, path: Path) -> None:
    """Write the report string to a file, creating parent dirs as needed.

    Args:
        report: The markdown report content.
        path: Destination file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def notify(message: str) -> None:
    """Send a notification via the Claude notification hook.

    Calls ``~/.claude/notify.sh`` with *message* as its first argument.
    Silently ignores errors (missing script, non-zero exit, etc.) so the
    pipeline never fails due to a notification problem.

    Args:
        message: Text passed to the notification script.
    """
    hook = Path.home() / ".claude" / "notify.sh"
    try:
        subprocess.run([str(hook), message], check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        # Script missing or not executable — nothing to do.
        pass
