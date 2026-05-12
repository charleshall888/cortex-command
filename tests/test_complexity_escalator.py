"""Unit and subprocess tests for ``bin/cortex-complexity-escalator``.

Covers Requirements 3–12 plus Edge Case line 100 (downgrade-then-re-escalate):

  R3  Gate 1 bullet shapes (Open Questions)
  R4  Gate 2 idiom exclusions (Open Decisions)
  R5  Thresholds (Gate 1 ≥2, Gate 2 ≥3)
  R6  Skip when already complex (including downgrade-then-re-escalate)
  R7  Three-payload-shape recognition
  R8  Event field shape (ts, event, feature, from, to, gate)
  R9  Read-after-write failure surface
  R10 Path-traversal rejection
  R11 Graceful no-ops (missing inputs, empty sections, missing events.log)
  R12 Announcement format strings

Mixes importlib-loaded internal-function unit tests and subprocess-driven
end-to-end exit-code tests per the ``test_resolve_backlog_item.py`` pattern.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-complexity-escalator"


@pytest.fixture(scope="module")
def escalator_module():
    """Load the executable script as an importable module for unit tests."""
    loader = importlib.machinery.SourceFileLoader(
        "complexity_escalator", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def tmp_lifecycle(tmp_path):
    """Create a self-contained ``lifecycle/<feature>/`` scratch directory.

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
    """R5: Gate 1 with 2 effective bullets escalates."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text("## Open Questions\n- q1?\n- q2?\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert "Escalating to Complex tier" in result.stdout
    assert tmp_lifecycle["events_log"].exists()


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
    assert "Escalating to Complex tier" in result.stdout


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
    research.write_text(
        "## Open Questions\n- q1?\n- q2?\n- q3?\n- q4?\n- q5?\n",
        encoding="utf-8",
    )
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
    research.write_text("## Open Questions\n- q1?\n- q2?\n", encoding="utf-8")
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
    research.write_text("## Open Questions\n- q1?\n- q2?\n", encoding="utf-8")
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
    research.write_text("## Open Questions\n- q1?\n- q2?\n", encoding="utf-8")
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_downgrade_then_reescalate(tmp_lifecycle):
    """R6 + Edge Cases line 100: downgrade-then-re-escalate re-fires the gate.

    Latest-event semantics: when the most recent complexity_override resolves
    to ``simple`` (manual downgrade after a prior escalation), the hook is no
    longer guarded and re-evaluates the section.
    """
    events = (
        json.dumps(
            {"event": "complexity_override", "from": "simple", "to": "complex"}
        )
        + "\n"
        + json.dumps(
            {"event": "complexity_override", "from": "complex", "to": "simple"}
        )
        + "\n"
    )
    tmp_lifecycle["events_log"].write_text(events, encoding="utf-8")
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        "## Open Questions\n- q1?\n- q2?\n- q3?\n- q4?\n- q5?\n",
        encoding="utf-8",
    )
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert "Escalating to Complex tier" in result.stdout
    # Verify a fresh escalate event was appended (3 events total now).
    lines = [
        line
        for line in tmp_lifecycle["events_log"]
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(lines) == 3
    last = json.loads(lines[-1])
    assert last["event"] == "complexity_override"
    assert last.get("to") == "complex"
    assert last.get("gate") == "research_open_questions"


# ---------------------------------------------------------------------------
# R8: Event field shape
# ---------------------------------------------------------------------------


def test_event_emission_shape(tmp_lifecycle):
    """R8: appended event JSON contains ts, event, feature, from, to, gate."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        "## Open Questions\n- q1?\n- q2?\n", encoding="utf-8"
    )
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    lines = [
        line
        for line in tmp_lifecycle["events_log"]
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert isinstance(entry.get("ts"), str)
    assert entry["event"] == "complexity_override"
    assert entry["feature"] == tmp_lifecycle["feature"]
    assert entry["from"] == "simple"
    assert entry["to"] == "complex"
    assert entry["gate"] == "research_open_questions"

    # Analogous Gate 2 invocation in a sibling feature directory.
    feature2 = "test-feature-2"
    dir2 = tmp_lifecycle["lifecycle_dir"] / feature2
    dir2.mkdir()
    (dir2 / "spec.md").write_text(
        "## Open Decisions\n- d1?\n- d2?\n- d3?\n", encoding="utf-8"
    )
    result2 = _run_script(
        feature2, "specify_open_decisions", tmp_lifecycle["tmp_path"]
    )
    assert result2.returncode == 0, result2.stderr
    events2 = (dir2 / "events.log").read_text(encoding="utf-8").splitlines()
    entry2 = json.loads([line for line in events2 if line.strip()][0])
    assert entry2["event"] == "complexity_override"
    assert entry2["gate"] == "specify_open_decisions"
    assert entry2["to"] == "complex"


# ---------------------------------------------------------------------------
# R9: Read-after-write failure
# ---------------------------------------------------------------------------


def test_read_after_write_failure(escalator_module, tmp_lifecycle, monkeypatch, capsys):
    """R9: verification failure surfaces non-zero exit + stderr; empty stdout.

    Monkeypatches the verification helper so the appended-then-verified event
    is reported as mismatched. Exercises the in-process ``main()`` entrypoint
    so the monkeypatch reaches the resolved helper.
    """
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        "## Open Questions\n- q1?\n- q2?\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        escalator_module,
        "_verify_last_event",
        lambda path, gate: (False, "read_after_write_mismatch"),
    )
    monkeypatch.chdir(tmp_lifecycle["tmp_path"])
    rc = escalator_module.main(
        [tmp_lifecycle["feature"], "--gate", "research_open_questions"]
    )
    captured = capsys.readouterr()
    assert rc != 0
    assert captured.out == ""
    assert "read_after_write_mismatch" in captured.err


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
    """R12: Gate 1 announcement matches the exact format string with N=4."""
    research = tmp_lifecycle["feature_dir"] / "research.md"
    research.write_text(
        "## Open Questions\n- q1?\n- q2?\n- q3?\n- q4?\n", encoding="utf-8"
    )
    result = _run_script(
        tmp_lifecycle["feature"], "research_open_questions", tmp_lifecycle["tmp_path"]
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == "Escalating to Complex tier — research surfaced 4 open questions\n"
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
        == "Escalating to Complex tier — spec contains 5 open decisions\n"
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
