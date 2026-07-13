"""Unit / golden / behavioral tests for the cortex-load-requirements verb.

Pins the selection set and the fallback string. Goldens for the uncontested
behaviors (substring match, ordering, skip-suffix) are hand-authored from the
prose algorithm in ``skills/lifecycle/references/load-requirements.md`` — NOT
captured from the verb's own output. For the behaviors the prose does not
settle — the two documented corrections (empty-tag strip; load-Global-Context-
in-fallback) and the GC-position-wins dedup rule — the expected values encode
the spec's deliberate resolution; there is no prose to author them from.

The verb is invoked via ``resolve()`` import or ``python3 -m`` subprocess —
never the bare ``cortex-load-requirements`` console-script name (which is not
on PATH until the wheel is reinstalled).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cortex_command.lifecycle.load_requirements_cli import resolve

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fallback string literal — written INDEPENDENTLY of the verb's constant (a
# typo in the verb's FALLBACK_NOTE_TEMPLATE must fail these tests; do NOT
# import the verb's constant and assert constant == constant).
EXPECTED_FALLBACK_EMPTY = "no area docs matched for tags: []; loaded project.md only"
EXPECTED_FALLBACK_SINGLE = "no area docs matched for tags: [foo]; loaded project.md only"
EXPECTED_FALLBACK_MULTI = "no area docs matched for tags: [foo, bar]; loaded project.md only"


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _write_repo(root, conditional=None, global_context=None, tags=None,
                slug="feat", touch_paths=True, make_project=True):
    """Materialize a synthetic repo and return the feature slug.

    ``conditional`` is a list of ``(trigger, path)``; ``global_context`` a list
    of paths; ``tags`` a list of tag strings (None ⇒ no index.md written).
    Referenced area-doc / Global-Context files are created so they resolve as
    present (no skip-suffix) unless ``touch_paths=False``.
    """
    conditional = conditional or []
    global_context = global_context or []
    req = root / "cortex" / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    if make_project:
        lines = ["# Project", "", "## Overview", "", "x", "",
                 "## Conditional Loading", ""]
        lines += [f"- {trig} → {path}" for trig, path in conditional]
        lines += ["", "## Global Context", ""]
        lines += [f"- {p}" for p in global_context]
        lines += ["", "## Optional", ""]
        (req / "project.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if touch_paths:
        for _, path in conditional:
            _touch(root, path)
        for path in global_context:
            _touch(root, path)
    if tags is not None:
        idx_dir = root / "cortex" / "lifecycle" / slug
        idx_dir.mkdir(parents=True, exist_ok=True)
        rendered = "[" + ", ".join(f'"{t}"' for t in tags) + "]"
        (idx_dir / "index.md").write_text(
            f"---\nfeature: {slug}\ntags: {rendered}\n---\n# {slug}\n",
            encoding="utf-8",
        )
    return slug


def _touch(root, relpath):
    f = root / relpath
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("", encoding="utf-8")


def _run(root, *args):
    env = dict(os.environ)
    env["CORTEX_REPO_ROOT"] = str(root)
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.load_requirements_cli", *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# R3 — input contract + byte-equality
# ---------------------------------------------------------------------------

def test_feature_matching_tags_loads_area_docs(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline/overnight", "cortex/requirements/pipeline.md")],
        tags=["pipeline"],
    )
    lines, note = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines  # positive control
    assert note is None


def test_feature_absent_index_falls_back(tmp_path):
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")],
                global_context=["cortex/requirements/glossary.md"])
    lines, note = resolve(tmp_path, "ghost-feature")
    assert "cortex/requirements/pipeline.md" not in lines
    assert lines[0] == "cortex/requirements/project.md"
    assert note == EXPECTED_FALLBACK_EMPTY


def test_no_feature_falls_back(tmp_path):
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")])
    lines, note = resolve(tmp_path, None)
    assert "cortex/requirements/pipeline.md" not in lines
    assert note == EXPECTED_FALLBACK_EMPTY


def test_feature_absent_index_byte_equals_no_feature(tmp_path):
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")],
                global_context=["cortex/requirements/glossary.md"])
    a = _run(tmp_path, "--feature", "ghost-feature")
    b = _run(tmp_path)
    assert a.returncode == 0 and b.returncode == 0
    assert a.stdout == b.stdout  # byte-for-byte
    assert a.stderr == b.stderr


# ---------------------------------------------------------------------------
# R4 — discriminating matching tests (negative paired with positive)
# ---------------------------------------------------------------------------

def test_empty_string_tag_loads_only_real_match(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("pipeline", "cortex/requirements/pipeline.md"),
            ("observability", "cortex/requirements/observability.md"),
        ],
        tags=["", "pipeline"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines          # positive
    assert "cortex/requirements/observability.md" not in lines  # not ALL
    # not none either — pipeline matched
    assert any(line.endswith("pipeline.md") for line in lines)


def test_trigger_only_match_not_path(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            # trigger contains "requirements" — positive control
            ("requirements gathering", "cortex/requirements/reqgather.md"),
            # path contains "requirements" but trigger does NOT — negative control
            ("deploy", "cortex/requirements/requirements-area.md"),
        ],
        tags=["requirements"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert "cortex/requirements/reqgather.md" in lines           # trigger match
    assert "cortex/requirements/requirements-area.md" not in lines  # path-only, no match


def test_whole_tag_not_split(tmp_path):
    cond = [("harness", "cortex/requirements/harness.md")]
    slug_neg = _write_repo(tmp_path / "neg", conditional=cond,
                           tags=["harness-adaptation"])
    lines_neg, _ = resolve(tmp_path / "neg", slug_neg)
    assert "cortex/requirements/harness.md" not in lines_neg  # whole-tag: not loaded

    slug_pos = _write_repo(tmp_path / "pos", conditional=cond, tags=["harness"])
    lines_pos, _ = resolve(tmp_path / "pos", slug_pos)
    assert "cortex/requirements/harness.md" in lines_pos       # exact tag: loaded


def test_pure_substring_axis(tmp_path):
    # tag 'pipe' is a substring of trigger token 'pipeline' → loads (pure
    # substring, NOT word-boundary). Pins the contract a word-boundary
    # implementation would violate.
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        tags=["pipe"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines


# ---------------------------------------------------------------------------
# R5 — output shape + dedup position
# ---------------------------------------------------------------------------

def _is_path_line(line):
    return line == line.strip() and (
        line.endswith(" (skipped: file absent)") or " " not in line
    )


def test_first_line_is_project_md(tmp_path):
    _write_repo(tmp_path, conditional=[("a", "cortex/requirements/a.md")])
    lines, _ = resolve(tmp_path, None)
    assert lines[0] == "cortex/requirements/project.md"


def test_stdout_is_paths_only(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        global_context=["cortex/requirements/glossary.md"],  # absent → skip-suffix
        tags=["pipeline"],
        touch_paths=False,
    )
    lines, _ = resolve(tmp_path, slug)
    for line in lines:
        assert _is_path_line(line), f"non-path line: {line!r}"


def test_dedup_global_context_position_wins(tmp_path):
    # A path that is BOTH a Global Context entry AND a tag-matched area doc is
    # emitted ONCE, in its Global Context position (right after project.md),
    # not appended after — assert position via a full ordered golden.
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/shared.md")],
        global_context=["cortex/requirements/shared.md"],
        tags=["pipeline"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/shared.md",
    ]


# ---------------------------------------------------------------------------
# R6 — goldens + fallback string (independent literal) + live oracle
# ---------------------------------------------------------------------------

def test_golden_match(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("statusline/dashboard", "cortex/requirements/observability.md"),
            ("pipeline", "cortex/requirements/pipeline.md"),
        ],
        global_context=["cortex/requirements/glossary.md"],
        tags=["pipeline"],
        touch_paths=True,
    )
    lines, note = resolve(tmp_path, slug)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/glossary.md",
        "cortex/requirements/pipeline.md",
    ]
    assert note is None


def test_golden_fallback_empty(tmp_path):
    _write_repo(tmp_path, conditional=[("a", "cortex/requirements/a.md")],
                global_context=["cortex/requirements/glossary.md"])
    lines, note = resolve(tmp_path, None)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/glossary.md",
    ]
    assert note == EXPECTED_FALLBACK_EMPTY


def test_fallback_string_single_and_multi(tmp_path):
    slug1 = _write_repo(tmp_path / "s", conditional=[("x", "cortex/requirements/x.md")],
                        tags=["foo"])
    _, note1 = resolve(tmp_path / "s", slug1)
    assert note1 == EXPECTED_FALLBACK_SINGLE

    slug2 = _write_repo(tmp_path / "m", conditional=[("x", "cortex/requirements/x.md")],
                        tags=["foo", "bar"])
    _, note2 = resolve(tmp_path / "m", slug2)
    assert note2 == EXPECTED_FALLBACK_MULTI


def test_dedup_multi_tag_one_phrase(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("statusline/dashboard/notifications",
                      "cortex/requirements/observability.md")],
        tags=["statusline", "dashboard"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert lines.count("cortex/requirements/observability.md") == 1


def test_unmatched_tag_dropped(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("observability", "cortex/requirements/observability.md"),
            ("pipeline", "cortex/requirements/pipeline.md"),
        ],
        tags=["nonexistent", "pipeline"],
    )
    lines, _ = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines
    assert "cortex/requirements/observability.md" not in lines


def test_live_project_md_format_invariants():
    # Format-realism: the live project.md uses slash-bulleted compound
    # triggers the synthetic fixtures don't. Drift-robust invariants only.
    lines, _ = resolve(REPO_ROOT, None)
    assert lines[0] == "cortex/requirements/project.md"
    for line in lines:
        assert _is_path_line(line), f"non-path line: {line!r}"


def test_live_conditional_loading_parses_compound_triggers():
    from cortex_command.lifecycle.load_requirements_cli import (
        _parse_conditional_loading,
    )
    text = (REPO_ROOT / "cortex/requirements/project.md").read_text(encoding="utf-8")
    pairs = _parse_conditional_loading(text)
    assert pairs, "no Conditional Loading bullets parsed from live project.md"
    # every path is repo-relative under cortex/requirements/; the split landed
    # the path on the right and kept the U+2192 out of both halves.
    for trigger, path in pairs:
        assert path.startswith("cortex/requirements/"), (trigger, path)
        assert "→" not in trigger and "→" not in path
    # at least one compound slash-trigger exercised the realistic format.
    assert any("/" in trigger for trigger, _ in pairs)


def test_live_project_md_selection_oracle(tmp_path):
    # Selection oracle over the LIVE project.md format (slash-compound
    # triggers), drift-robust: the expected pick is COMPUTED from the live
    # file at test time (not frozen), so a future project.md edit cannot
    # produce a false RED. Copy live project.md into a tmp repo so a synthetic
    # index can attach without polluting the real repo.
    import re as _re
    from cortex_command.lifecycle.load_requirements_cli import (
        _parse_conditional_loading,
    )
    live = (REPO_ROOT / "cortex/requirements/project.md").read_text(encoding="utf-8")
    pairs = _parse_conditional_loading(live)
    assert pairs, "live project.md has no Conditional Loading pairs"
    trigger, path = pairs[0]
    token = _re.findall(r"[a-z]+", trigger.lower())[0]  # a real word from the trigger

    req = tmp_path / "cortex" / "requirements"
    req.mkdir(parents=True)
    (req / "project.md").write_text(live, encoding="utf-8")
    _touch(tmp_path, path)  # the selected area doc exists → no skip-suffix
    idx = tmp_path / "cortex" / "lifecycle" / "live"
    idx.mkdir(parents=True)
    (idx / "index.md").write_text(f'---\ntags: ["{token}"]\n---\n', encoding="utf-8")

    lines, note = resolve(tmp_path, "live")
    assert path in lines, (
        f"tag {token!r} (from live trigger {trigger!r}) should select {path}"
    )
    assert note is None  # a real match → no fallback note


def test_absent_glossary_literal_resolution(tmp_path):
    # R8: a referenced-but-absent Global Context doc emits its FULL repo-relative
    # path + skip-suffix — proving literal resolution, not a bare-filename
    # heuristic. Hermetic (tmp tree) so it does not depend on the live repo
    # lacking glossary.md, which now exists as a real area doc.
    _write_repo(
        tmp_path,
        global_context=["cortex/requirements/glossary.md"],
        touch_paths=False,  # glossary.md deliberately absent → skip-suffix
    )
    lines, _ = resolve(tmp_path, None)
    assert "cortex/requirements/glossary.md (skipped: file absent)" in lines


# ---------------------------------------------------------------------------
# R7 — no events emission (behavioral)
# ---------------------------------------------------------------------------

def test_verb_writes_no_events_log(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        tags=["pipeline"],
    )
    events = tmp_path / "cortex" / "lifecycle" / slug / "events.log"
    events.write_text('{"event": "preexisting"}\n', encoding="utf-8")
    before = events.stat().st_mtime_ns
    proc = _run(tmp_path, "--feature", slug)
    assert proc.returncode == 0
    after = events.stat().st_mtime_ns
    assert before == after, "verb modified events.log"
    # no stray events.log created elsewhere under the repo
    found = list(tmp_path.rglob("events.log"))
    assert found == [events], f"unexpected events.log files: {found}"
