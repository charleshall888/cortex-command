"""Unit and subprocess tests for ``cortex-complexity-escalator``.

Covers Requirements 3–12 plus Edge Case line 100 (downgrade-then-re-escalate):

  R3  Gate 1 bullet shapes (Open Questions)
  R4  Gate 2 idiom exclusions (Open Decisions)
  R5  Thresholds (Gate 1 ≥8, Gate 2 ≥3)
  R6  Skip when already complex (including downgrade-then-re-escalate)
      plus the --allow-downgrade reverse transition
  R7  Three-payload-shape recognition
  R10 Path-traversal rejection
  R11 Graceful no-ops (missing inputs, empty sections, missing events.log)
  R12 Announcement format strings

Mixes direct-import unit tests (importing from
``cortex_command.lifecycle.complexity_escalator``) and subprocess-driven
end-to-end exit-code tests per the ``test_resolve_backlog_item.py`` pattern.

The ``escalator_module`` fixture returns the Python module directly (no longer
loads the bin file, which is now a dual-channel bash wrapper after the
Task 15 promotion).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import cortex_command.lifecycle.complexity_escalator as _escalator_module

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-complexity-escalator"


@pytest.fixture(scope="module")
def escalator_module():
    """Return the complexity_escalator Python module for unit tests."""
    return _escalator_module


@pytest.fixture
def tmp_lifecycle(tmp_path):
    """Create a self-contained ``cortex/lifecycle/<feature>/`` scratch directory.

    Returns a dict carrying the repo-root tmp path, the lifecycle dir, the
    feature slug, the feature dir, and the (not-yet-created) events.log path.
    """
    feature = "test-feature"
    lifecycle_dir = tmp_path / "cortex" / "lifecycle"
    feature_dir = lifecycle_dir / feature
    feature_dir.mkdir(parents=True)
    return {
        "tmp_path": tmp_path,
        "lifecycle_dir": lifecycle_dir,
        "feature": feature,
        "feature_dir": feature_dir,
        "events_log": feature_dir / "events.log",
    }


def _run_script(feature, gate, cwd, extra_args=None):
    """Invoke the script via subprocess; return CompletedProcess."""
    args = [sys.executable, str(SCRIPT_PATH)] if False else [str(SCRIPT_PATH)]
    args = [str(SCRIPT_PATH), feature, "--gate", gate]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


EIGHT = "\n".join(f"- q{i}?" for i in range(1, 9))
"""Eight open questions — the Gate 1 threshold, used wherever a test needs a firing section."""


# ---------------------------------------------------------------------------
# R3: Gate 1 bullet counting
# ---------------------------------------------------------------------------

GATE1_BULLET_CASES = [
    pytest.param(
        "## Open Questions\n- dash bullet question?\n- second?\n",
        2,
        id="dash_bullet",
    ),
    pytest.param(
        "## Open Questions\n* star bullet question?\n* second?\n",
        2,
        id="star_bullet",
    ),
    pytest.param(
        "## Open Questions\n1. numbered question?\n2. second numbered?\n",
        2,
        id="numbered_bullet",
    ),
    pytest.param(
        "## Open Questions\n- parent question?\n  - nested sub-bullet excluded\n  - another nested\n",
        1,
        id="nested_subbullet_excluded",
    ),
    pytest.param(
        "## Open Questions\n```\n- fenced bullet excluded\n- also excluded\n```\n",
        0,
        id="fenced_code_block_excluded",
    ),
    pytest.param(
        "## Open Questions\n> - blockquoted bullet excluded\n> - also excluded\n",
        0,
        id="blockquoted_bullet_excluded",
    ),
]


@pytest.mark.parametrize("text,expected", GATE1_BULLET_CASES)
def test_open_questions_bullet_counting(escalator_module, text, expected):
    """R3: Gate 1 counter handles dash, star, numbered, nested, fenced, blockquoted."""
    section_lines = escalator_module._slice_section(text, "## Open Questions")
    count = escalator_module._count_top_level_bullets(
        section_lines, escalator_module.GATE_RESEARCH
    )
    assert count == expected


# ---------------------------------------------------------------------------
# R4: Gate 2 idiom exclusions
# ---------------------------------------------------------------------------

GATE2_BULLET_CASES = [
    pytest.param(
        "## Open Decisions\n- [Only when implementation-level context is required...]\n",
        0,
        id="template_placeholder_bracket",
    ),
    pytest.param(
        "## Open Decisions\n- None.\n",
        0,
        id="none_dot_capital",
    ),
    pytest.param(
        "## Open Decisions\n- (none)\n",
        0,
        id="paren_none_lowercase",
    ),
    pytest.param(
        "## Open Decisions\n- Should we use Postgres or SQLite for storage?\n",
        1,
        id="real_decision_counted",
    ),
    pytest.param(
        "## Open Decisions\n- none.\n",
        0,
        id="none_dot_lowercase",
    ),
    pytest.param(
        "## Open Decisions\n- (None of the above)\n",
        0,
        id="paren_None_capital_with_trailing",
    ),
]


@pytest.mark.parametrize("text,expected", GATE2_BULLET_CASES)
def test_open_decisions_bullet_counting(escalator_module, text, expected):
    """R4: Gate 2 idiom exclusions for [..], None., (none), with capitalization variants."""
    section_lines = escalator_module._slice_section(text, "## Open Decisions")
    count = escalator_module._count_top_level_bullets(
        section_lines, escalator_module.GATE_SPECIFY
    )
    assert count == expected


# ---------------------------------------------------------------------------
# R5: Thresholds
# ---------------------------------------------------------------------------


def test_threshold_gate1_below(tmp_lifecycle):
    """R5: Gate 1 with 1 effective bullet does not escalate."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("## Open Questions\n- only one question?\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_threshold_gate1_at(tmp_lifecycle):
    """R5: Gate 1 at the threshold (8 effective bullets) escalates."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert "Consider Complex tier" in result.stdout
    # Advisory: the recommendation is stdout only, never a written event.
    assert not tmp_lifecycle["events_log"].exists()


def test_threshold_gate2_below(tmp_lifecycle):
    """R5: Gate 2 with 2 effective bullets does not escalate."""
    spec = tmp_lifecycle["feature_dir"] / "spec.md"
    spec.write_text("## Open Decisions\n- d1?\n- d2?\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "specify_open_decisions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_threshold_gate2_at(tmp_lifecycle):
    """R5: Gate 2 with 3 effective bullets escalates."""
    spec = tmp_lifecycle["feature_dir"] / "spec.md"
    spec.write_text(
        "## Open Decisions\n- d1?\n- d2?\n- d3?\n", encoding="utf-8"
    )
    result = _run_script(
        tmp_lifecycle["feature"], "specify_open_decisions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert "Consider Complex tier" in result.stdout


# ---------------------------------------------------------------------------
# R6: Skip when already complex
# ---------------------------------------------------------------------------


def test_skip_when_already_complex(tmp_lifecycle):
    """R6: pre-existing complexity_override event suppresses re-escalation."""
    tmp_lifecycle["events_log"].write_text(
        json.dumps(
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "complexity_override",
                "feature": tmp_lifecycle["feature"],
                "from": "simple",
                "to": "complex",
                "gate": "research_open_questions",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    before = tmp_lifecycle["events_log"].read_text(encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    after = tmp_lifecycle["events_log"].read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# R7: Three-payload-shape recognition
# ---------------------------------------------------------------------------


def test_skip_recognizes_payload_shape_standard(tmp_lifecycle):
    """R7: standard {event, from, to} payload triggers skip."""
    tmp_lifecycle["events_log"].write_text(
        json.dumps(
            {"event": "complexity_override", "from": "simple", "to": "complex"}
        )
        + "\n",
        encoding="utf-8",
    )
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_skip_recognizes_payload_shape_yaml_style(tmp_lifecycle):
    """R7: bare {event: complexity_override} (no from/to) triggers skip."""
    tmp_lifecycle["events_log"].write_text(
        json.dumps({"event": "complexity_override"}) + "\n",
        encoding="utf-8",
    )
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_skip_recognizes_payload_shape_tier(tmp_lifecycle):
    """R7: {event: complexity_override, tier: complex} triggers skip."""
    tmp_lifecycle["events_log"].write_text(
        json.dumps({"event": "complexity_override", "tier": "complex"}) + "\n",
        encoding="utf-8",
    )
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""




# ---------------------------------------------------------------------------
# R8: Event field shape
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# R9: Read-after-write failure
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# R2 (#374): read-after-write verifier matches anywhere, not by file tail
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# R10: Path-traversal rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_slug",
    ["../foo", "foo/bar", ".."],
    ids=["dotdot_slash_foo", "foo_slash_bar", "dotdot"],
)
def test_path_traversal_rejection(tmp_lifecycle, bad_slug):
    """R10: slugs that fail the regex or escape lifecycle/ are rejected non-zero."""
    result = _run_script(
        bad_slug, "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode != 0
    assert result.stderr != ""


def test_path_traversal_rejection_positive(tmp_lifecycle):
    """R10: a valid slug pointing at a valid lifecycle dir proceeds normally."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("## Open Questions\n- only one?\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# R11: Graceful no-ops on missing inputs
# ---------------------------------------------------------------------------


def test_missing_inputs_graceful_no_research_md(tmp_lifecycle):
    """R11: research.md absent → exit 0, empty std streams, no events.log."""
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_missing_inputs_graceful_no_heading(tmp_lifecycle):
    """R11: research.md present, ``## Open Questions`` heading absent."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("# Just a title\n\nSome prose, no headings.\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_missing_inputs_graceful_empty_section(tmp_lifecycle):
    """R11: heading present but section empty (no bullets)."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("## Open Questions\n\n## Next Section\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_missing_inputs_graceful_all_excluded(tmp_lifecycle):
    """R11: section present but bullets are all excluded (effective count = 0)."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        "## Open Questions\n"
        "  - indented sub-bullet only\n"
        "```\n- fenced excluded\n```\n"
        "> - blockquoted excluded\n",
        encoding="utf-8",
    )
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not tmp_lifecycle["events_log"].exists()


def test_missing_inputs_graceful_events_log_absent(tmp_lifecycle):
    """R11: events.log absent (fresh feature) + below-threshold input → no mutation."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("## Open Questions\n- single question?\n", encoding="utf-8")
    assert not tmp_lifecycle["events_log"].exists()
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not tmp_lifecycle["events_log"].exists()


# ---------------------------------------------------------------------------
# R12: Announcement format
# ---------------------------------------------------------------------------


def test_announcement_format_gate1(tmp_lifecycle):
    """R12: Gate 1 announcement matches the exact format string with N=8."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(f"## Open Questions\n{EIGHT}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == "Consider Complex tier — research surfaced 8 unresolved questions\n"
    )


def test_announcement_format_gate2(tmp_lifecycle):
    """R12: Gate 2 announcement matches the exact format string with N=5."""
    spec = tmp_lifecycle["feature_dir"] / "spec.md"
    spec.write_text(
        "## Open Decisions\n- d1?\n- d2?\n- d3?\n- d4?\n- d5?\n",
        encoding="utf-8",
    )
    result = _run_script(
        tmp_lifecycle["feature"], "specify_open_decisions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == "Consider Complex tier — spec contains 5 unresolved decisions\n"
    )


# ---------------------------------------------------------------------------
# R2: Unknown --gate argument
# ---------------------------------------------------------------------------


def test_unknown_gate_argument(tmp_lifecycle):
    """R2: invalid --gate value exits non-zero with stderr mentioning the gate."""
    result = subprocess.run(
        [str(SCRIPT_PATH), "valid-slug", "--gate", "invalid_gate"],
        cwd=str(tmp_lifecycle["tmp_path"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "invalid_gate" in result.stderr or "invalid choice" in result.stderr


# ---------------------------------------------------------------------------
# Threshold recalibration: Gate 1 fires at 8, not 2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n,should_fire",
    [(2, False), (6, False), (7, False), (8, True), (9, True)],
)
def test_gate1_threshold_is_eight(tmp_lifecycle, n, should_fire):
    """Gate 1 fires only at >= 8 unresolved questions.

    The original threshold of 2 fired on 97% of real features (median 6),
    which made 'complex' the default rather than the exception.
    """
    research = tmp_lifecycle["feature_dir"] / "research.md"
    body = "\n".join(f"- q{i}?" for i in range(1, n + 1))
    research.write_text(f"## Open Questions\n{body}\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert bool(result.stdout.strip()) is should_fire
    assert not tmp_lifecycle["events_log"].exists()


# ---------------------------------------------------------------------------
# Unresolved-only counting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("## Open Questions\n- [x] settled\n- [X] also settled\n- live?\n", 1),
        ("## Open Questions\n- ~~withdrawn~~\n- live?\n", 1),
        ("## Open Questions\n- RESOLVED: we use flock\n- live?\n", 1),
        ("## Open Questions\n- RESOLVED — we use flock\n- live?\n", 1),
        ("## Open Questions\n- DEFERRED\n- live?\n", 1),
        ("## Open Questions\n- **RESOLVED** — bolded marker\n- live?\n", 1),
        ("## Open Questions\n- ✓ handled\n- live?\n", 1),
        ("## Open Questions\n- [ ] unticked box is still live?\n", 1),
        # Gate 1 previously lacked the "nothing here" idioms entirely.
        ("## Open Questions\n- None.\n", 0),
        ("## Open Questions\n- (none)\n", 0),
        ("## Open Questions\n- [Placeholder prose in brackets]\n", 0),
    ],
)
def test_unresolved_only_counting(escalator_module, text, expected):
    """Settled bullets and 'nothing here' idioms do not count toward the gate."""
    section_lines = escalator_module._slice_section(text, "## Open Questions")
    assert (
        escalator_module._count_top_level_bullets(
            section_lines, escalator_module.GATE_RESEARCH
        )
        == expected
    )


def test_research_that_answers_itself_does_not_escalate(tmp_lifecycle):
    """Ten questions, nine of them resolved, stays at simple tier."""
    resolved = "\n".join(f"- RESOLVED: q{i} — answered inline" for i in range(1, 10))
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        f"## Open Questions\n{resolved}\n- one genuinely open question?\n",
        encoding="utf-8",
    )
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not tmp_lifecycle["events_log"].exists()


# ---------------------------------------------------------------------------
# De-escalation (--allow-downgrade)
# ---------------------------------------------------------------------------
















@pytest.mark.parametrize(
    "bullet",
    [
        "- Deferred rendering: should we adopt it for the water pass?",
        "- Resolved dependencies are ambiguous — which lockfile wins?",
        "- Decided behaviour for the null case is unclear, what should it be?",
        "- Answered prayers aside, what is the retry budget?",
        "- Deferring this question: is that allowed?",
        "- resolved: lowercase is not a tag, this still counts?",
    ],
)
def test_resolution_markers_do_not_swallow_real_questions(escalator_module, bullet):
    """A question that merely BEGINS with a marker word is still a question.

    Regression guard: matching the markers case-insensitively with a bare word
    boundary silently excluded genuine open questions — 'Deferred rendering:
    should we adopt it?' is a question, not a deferral. Markers must be
    ALL-CAPS and delimited to count as a tag.
    """
    section_lines = escalator_module._slice_section(
        f"## Open Questions\n{bullet}\n", "## Open Questions"
    )
    assert (
        escalator_module._count_top_level_bullets(
            section_lines, escalator_module.GATE_RESEARCH
        )
        == 1
    )
