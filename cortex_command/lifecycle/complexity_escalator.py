"""Report a complexity signal for a lifecycle feature. Advisory only.

Counts *unresolved* top-level bullets under ``## Open Questions`` (Gate 1) or
``## Open Decisions`` (Gate 2) and, when the count meets the gate's threshold
AND the feature is not already ``complex``, prints a one-line recommendation to
stdout. On every other path it exits 0 silently.

**It writes nothing.** The tier is the assessment's to set, not a bullet
count's: the count measures how much uncertainty got written down, which is not
the same as how hard the work is. The caller re-assesses with the research in
hand and records any change itself via ``cortex-lifecycle-event
complexity-override``. This hook previously appended the override directly,
which made the counter the decider and left the assessment no way to disagree.

Bullets the author has already settled — ``[x]``, ``~~struck~~``, ``✓``, or a
leading ALL-CAPS RESOLVED/ANSWERED/DECIDED/DEFERRED tag — do not count,
matching the Research exit gate in
``skills/refine/references/research-phase.md``, which requires every open
question to be resolved or deferred before Spec. The word markers must be
ALL-CAPS and delimited (bolded, or followed by a colon, a dash, or
end-of-line) so that a question merely *beginning* with one of those words
("Deferred rendering: should we adopt it?") still counts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional



GATE_RESEARCH = "research_open_questions"
GATE_SPECIFY = "specify_open_decisions"

GATE_CONFIG = {
    GATE_RESEARCH: {
        "artifact": "research.md",
        "section": "## Open Questions",
        # Set well above a typical feature's open-question count. A gate that
        # fires on nearly everything is detecting that research happened, not
        # that the work is hard; escalation has to stay exceptional to mean
        # anything. Repos with a different research style should tune this.
        "threshold": 8,
        "noun": "research surfaced {n} unresolved questions",
    },
    GATE_SPECIFY: {
        "artifact": "spec.md",
        "section": "## Open Decisions",
        "threshold": 3,
        "noun": "spec contains {n} unresolved decisions",
    },
}

SLUG_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# Kept in lockstep with ``common.TIER_VOCABULARY``. Duplicated rather than
# imported so this hook stays importable from the bin wrapper without pulling
# the wider package in.
_TIER_VOCABULARY = frozenset({"simple", "moderate", "complex"})


def read_effective_tier(events_log_path: Path) -> str:
    """Return the effective complexity tier per latest-event semantics.

    Mirrors the canonical reduction in ``lifecycle/state_cli.py``:
    ``lifecycle_start.tier`` superseded by ``complexity_override.to``, whichever
    appears most recently. Recognizes the three historical override payload
    shapes: ``tier`` field, ``to`` field, or neither (bare presence implies an
    escalation).

    Returns ``"simple"`` when the log is absent or carries no tier at all — the
    rank floor, so a missing log never suppresses the advisory.
    """
    if not events_log_path.exists():
        return "simple"

    latest_tier = "simple"
    try:
        with open(events_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                event = obj.get("event")
                if event == "lifecycle_start":
                    tier = obj.get("tier")
                    if isinstance(tier, str) and tier:
                        latest_tier = tier
                    continue
                if event != "complexity_override":
                    continue
                if "tier" in obj:
                    latest_tier = obj["tier"]
                elif "to" in obj:
                    latest_tier = obj["to"]
                else:
                    latest_tier = "complex"
    except OSError:
        return "simple"

    return latest_tier


def _is_fence_line(line: str) -> bool:
    """Return True if a stripped line opens or closes a fenced code block."""
    stripped = line.lstrip()
    if stripped.startswith("> "):
        return False
    return stripped.startswith("```")


def _is_heading_line(line: str) -> bool:
    """Return True if the line is a Markdown ATX heading (1-6 hashes + space)."""
    return bool(re.match(r"^#{1,6} ", line))


def _slice_section(text: str, heading: str) -> list[str]:
    """Return the lines of ``text`` belonging to the named section.

    Walks the file once, tracking fenced-block state, and locates the
    target heading by exact match on a non-fenced stripped line. Collects
    lines after that heading until the next non-fenced ATX heading or EOF.
    Returns ``[]`` if the heading is absent.
    """
    lines = text.splitlines()
    fence_open = False
    section_start = -1

    for idx, line in enumerate(lines):
        if _is_fence_line(line) and not line.lstrip().startswith("> "):
            fence_open = not fence_open
            continue
        if fence_open:
            continue
        if line.rstrip() == heading:
            section_start = idx + 1
            break

    if section_start < 0:
        return []

    # Now collect lines after the heading until next heading or EOF, with
    # its own fence-tracking state.
    section_lines: list[str] = []
    fence_open = False
    for line in lines[section_start:]:
        is_fence = _is_fence_line(line) and not line.lstrip().startswith("> ")
        if not fence_open and not is_fence and _is_heading_line(line):
            break
        section_lines.append(line)
        if is_fence:
            fence_open = not fence_open

    return section_lines


def _count_top_level_bullets(section_lines: list[str], gate: str) -> int:
    """Count *unresolved* top-level bullets in a section slice.

    Excludes lines inside fenced code blocks, blockquoted lines (``> ``),
    and indented (sub-bullet) lines.

    Both gates exclude the "nothing here" idioms — bracketed placeholder,
    ``None.`` / ``none.``, and ``([Nn]one ...)``. These were originally
    Gate-2-only, which let a Gate 1 section reading ``- None.`` count as a
    real open question.

    Both gates also exclude bullets the author has marked as already settled
    (``[x]``, ``~~struck~~``, or a leading RESOLVED/ANSWERED/DECIDED tag), so
    research that answers its own questions no longer escalates the tier.
    """
    fence_open = False
    count = 0
    bullet_re = re.compile(r"^(?:[-*]|\d+\.[ \t])")
    none_re = re.compile(r"^[Nn]one\b")
    paren_none_re = re.compile(r"^\([Nn]one\b")
    bullet_marker_strip_re = re.compile(r"^(?:[-*]|\d+\.)[ \t]+")
    # Vocabulary matches the Research exit gate in
    # skills/refine/references/research-phase.md, which already asks the author
    # to resolve or defer every open question before Spec. Counting settled
    # items put the gate at odds with that instruction.
    #
    # The word markers must be ALL-CAPS *and* delimited (bolded, or followed by
    # a colon/dash/end-of-line) so they read as a tag rather than a sentence
    # opener. Case-insensitive matching silently swallowed real questions —
    # "Deferred rendering: should we adopt it?" is a question, not a deferral.
    resolved_re = re.compile(
        r"^(?:"
        r"\[[xX]\]"
        r"|~~"
        r"|✓|✅"
        r"|\*\*(?:RESOLVED|ANSWERED|DECIDED|DEFERRED)\b"
        r"|(?:RESOLVED|ANSWERED|DECIDED|DEFERRED)(?=\s*[:—–-]|\s*$)"
        r")"
    )

    for line in section_lines:
        is_fence = _is_fence_line(line) and not line.lstrip().startswith("> ")
        if is_fence:
            fence_open = not fence_open
            continue
        if fence_open:
            continue
        stripped_left = line.lstrip()
        if stripped_left.startswith("> "):
            continue
        if line and (line[0] == " " or line[0] == "\t"):
            # Indented => sub-bullet; excluded
            continue
        if not bullet_re.match(stripped_left):
            continue
        # Counted as a top-level bullet; apply the content exclusions.
        body = bullet_marker_strip_re.sub("", stripped_left, count=1)
        if body.startswith("["):
            # Bracketed placeholder, or a `[x]`/`[ ]` task marker. A ticked
            # box is settled; an unticked one is still a live question.
            if not re.match(r"^\[[ ]?\]", body):
                continue
            body = re.sub(r"^\[[ ]?\][ \t]*", "", body, count=1)
        if none_re.match(body):
            continue
        if paren_none_re.match(body):
            continue
        if resolved_re.match(body):
            continue
        count += 1
    return count


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-complexity-escalator",
        description=(
            "Evaluate a complexity-escalation gate for a lifecycle feature. "
            "Reads research.md (--gate research_open_questions) or spec.md "
            "(--gate specify_open_decisions), counts top-level bullets in the "
            "relevant section, and on threshold append a complexity_override "
            "event with read-after-write verification."
        ),
    )
    parser.add_argument(
        "feature",
        help="Feature slug under cortex/lifecycle/ (e.g., my-feature-name).",
    )
    parser.add_argument(
        "--gate",
        required=True,
        choices=[GATE_RESEARCH, GATE_SPECIFY],
        help=(
            "Which gate to evaluate. Use research_open_questions for Gate 1 "
            "(Research → Specify) or specify_open_decisions for Gate 2 "
            "(Specify → Plan)."
        ),
    )
    parser.add_argument(
        "--lifecycle-dir",
        default="cortex/lifecycle",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    feature = args.feature
    gate = args.gate
    lifecycle_dir = Path(args.lifecycle_dir)

    # R10: slug + path hardening.
    if not SLUG_RE.match(feature):
        sys.stderr.write(f"rejected feature slug: {feature!r}\n")
        return 2
    feature_dir = lifecycle_dir / feature
    try:
        real_feature = os.path.realpath(feature_dir)
        real_lifecycle = os.path.realpath(lifecycle_dir)
    except OSError as exc:
        sys.stderr.write(f"realpath failure for {feature!r}: {exc}\n")
        return 2
    if not real_feature.startswith(real_lifecycle + os.sep):
        sys.stderr.write(f"rejected feature slug: {feature!r}\n")
        return 2

    cfg = GATE_CONFIG[gate]
    artifact_path = feature_dir / cfg["artifact"]
    events_log_path = feature_dir / "events.log"

    # Tier guard via latest-event semantics — read only, never written.
    if read_effective_tier(events_log_path) == "complex":
        return 0

    # R11: graceful no-op when the artifact is missing or the section absent.
    if not artifact_path.exists():
        return 0

    try:
        text = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"failed to read {artifact_path}: {exc}\n")
        return 2

    section_lines = _slice_section(text, cfg["section"])
    if not section_lines:
        return 0

    count = _count_top_level_bullets(section_lines, gate)
    if count < cfg["threshold"]:
        return 0

    # Advisory only. This hook reports a signal; it does not decide the tier and
    # writes nothing. The caller re-assesses with the research in hand and, if it
    # changes its mind, records that itself via
    # ``cortex-lifecycle-event complexity-override``. A bullet count is evidence
    # about how much uncertainty got written down, which is not the same thing as
    # how hard the work is — it should inform the assessment, not replace it.
    sys.stdout.write(
        "Consider Complex tier — " + cfg["noun"].format(n=count) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
