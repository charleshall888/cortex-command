"""Unit / golden / behavioral tests for the cortex-load-requirements verb.

Pins the selection set, the coverage tiers, and the stderr note strings.
Selection is exact kebab-normalized key lookup of a lifecycle index's
``areas:`` against the ``## Conditional Loading`` area-to-doc map; the two
documented corrections (empty-entry strip; load-Global-Context-in-fallback)
and the GC-position-wins dedup rule encode the spec's deliberate resolution.

The verb is invoked via ``resolve()`` import or ``python3 -m`` subprocess —
never the bare ``cortex-load-requirements`` console-script name (which resolves
to the released wheel, not this working tree).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from cortex_command.lifecycle.load_requirements_cli import (
    COVERAGE_MARKER_PREFIX,
    resolve,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Note literals — written INDEPENDENTLY of the verb's constants (a typo in a
# template must fail these tests; do NOT import the verb's constant and assert
# constant == constant).
EXPECTED_FALLBACK = (
    "no areas declared for this feature; loaded project.md + Global Context only"
)
EXPECTED_NO_INDEX = (
    "no lifecycle index at cortex/lifecycle/ghost-feature/index.md, so no areas "
    "were available; loaded project.md + Global Context only — area coverage is "
    "UNVERIFIED, not empty"
)

COVERAGE_RE = re.compile(r"^COVERAGE:(loaded|doc-missing|unmapped|no-area)$")
ARROW_LITERAL = "→"


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _write_repo(root, conditional=None, global_context=None, areas=None,
                slug="feat", touch_paths=True, make_project=True):
    """Materialize a synthetic repo and return the feature slug.

    ``conditional`` is a list of ``(key_text, path)``; ``global_context`` a
    list of paths; ``areas`` a list of area strings (None ⇒ no index.md
    written). Referenced area-doc / Global-Context files are created so they
    resolve as present (no skip-suffix) unless ``touch_paths=False``.
    """
    conditional = conditional or []
    global_context = global_context or []
    req = root / "cortex" / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    if make_project:
        lines = ["# Project", "", "## Overview", "", "x", "",
                 "## Conditional Loading", ""]
        lines += [f"- {keys} → {path}" for keys, path in conditional]
        lines += ["", "## Global Context", ""]
        lines += [f"- {p}" for p in global_context]
        lines += ["", "## Optional", ""]
        (req / "project.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if touch_paths:
        for _, path in conditional:
            _touch(root, path)
        for path in global_context:
            _touch(root, path)
    if areas is not None:
        idx_dir = root / "cortex" / "lifecycle" / slug
        idx_dir.mkdir(parents=True, exist_ok=True)
        rendered = "[" + ", ".join(f'"{a}"' for a in areas) + "]"
        (idx_dir / "index.md").write_text(
            f'---\nfeature: {slug}\ntags: ["ignored"]\nareas: {rendered}\n---\n'
            f"# {slug}\n",
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


def _marker_lines(stderr):
    return [line for line in stderr.splitlines() if COVERAGE_RE.match(line)]


# ---------------------------------------------------------------------------
# R3 — input contract + byte-equality
# ---------------------------------------------------------------------------

def test_feature_matching_areas_loads_area_docs(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline, overnight-runner", "cortex/requirements/pipeline.md")],
        areas=["pipeline"],
    )
    lines, note, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines  # positive control
    assert note is None
    assert coverage == "loaded"


def test_feature_absent_index_falls_back(tmp_path):
    """A NAMED feature whose index is absent says so — coverage is unverified.

    Distinct from the area-mismatch note: a bare project.md result must not
    read the same when coverage was never determined as when it was determined
    to be empty. Only the first is repairable, and at a fresh refine (before
    the index is written) it is the case that actually occurs.
    """
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")],
                global_context=["cortex/requirements/glossary.md"])
    lines, note, coverage = resolve(tmp_path, "ghost-feature")
    assert "cortex/requirements/pipeline.md" not in lines
    assert lines[0] == "cortex/requirements/project.md"
    assert note == EXPECTED_NO_INDEX
    assert note != EXPECTED_FALLBACK  # the distinction is the point
    assert coverage == "no-area"


def test_no_feature_falls_back(tmp_path):
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")])
    lines, note, coverage = resolve(tmp_path, None)
    assert "cortex/requirements/pipeline.md" not in lines
    assert note == EXPECTED_FALLBACK
    assert coverage == "no-area"


def test_feature_absent_index_selects_same_docs_as_no_feature(tmp_path):
    """Same SELECTION as the argless call, deliberately different note.

    stdout must stay byte-identical — an absent index changes nothing about
    which docs load. stderr must not: naming a feature whose index is missing
    is the repairable case, while omitting --feature entirely is discovery's
    normal argless call and keeps the plain no-area note.
    """
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")],
                global_context=["cortex/requirements/glossary.md"])
    a = _run(tmp_path, "--feature", "ghost-feature")
    b = _run(tmp_path)
    assert a.returncode == 0 and b.returncode == 0
    assert a.stdout == b.stdout  # byte-for-byte
    assert a.stderr.splitlines()[0] == EXPECTED_NO_INDEX
    assert b.stderr.splitlines()[0] == EXPECTED_FALLBACK
    assert a.stderr != b.stderr
    assert _marker_lines(a.stderr) == ["COVERAGE:no-area"]
    assert _marker_lines(b.stderr) == ["COVERAGE:no-area"]


# ---------------------------------------------------------------------------
# R4 — discriminating matching tests (negative paired with positive)
# ---------------------------------------------------------------------------

def test_empty_string_area_loads_only_real_match(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("pipeline", "cortex/requirements/pipeline.md"),
            ("observability", "cortex/requirements/observability.md"),
        ],
        areas=["", "pipeline"],
    )
    lines, _, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines          # positive
    assert "cortex/requirements/observability.md" not in lines  # not ALL
    assert coverage == "loaded"


def test_keys_match_not_paths(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            # a declared key — positive control
            ("requirements", "cortex/requirements/reqgather.md"),
            # path contains "requirements" but no key does — negative control
            ("deploy", "cortex/requirements/requirements-area.md"),
        ],
        areas=["requirements"],
    )
    lines, _, _ = resolve(tmp_path, slug)
    assert "cortex/requirements/reqgather.md" in lines            # key match
    assert "cortex/requirements/requirements-area.md" not in lines  # path-only


def test_area_is_not_split_into_words(tmp_path):
    cond = [("harness", "cortex/requirements/harness.md")]
    slug_neg = _write_repo(tmp_path / "neg", conditional=cond,
                           areas=["harness-adaptation"])
    lines_neg, _, cov_neg = resolve(tmp_path / "neg", slug_neg)
    assert "cortex/requirements/harness.md" not in lines_neg  # whole key only
    assert cov_neg == "unmapped"

    slug_pos = _write_repo(tmp_path / "pos", conditional=cond, areas=["harness"])
    lines_pos, _, cov_pos = resolve(tmp_path / "pos", slug_pos)
    assert "cortex/requirements/harness.md" in lines_pos       # exact key
    assert cov_pos == "loaded"


def test_exact_key_lookup_rejects_substring(tmp_path):
    """Spec R7's first trap: the area ``pipe`` loads NO area doc.

    Pins the contract the retired substring selector violated — ``pipe`` is a
    substring of the key ``pipeline`` and used to select ``pipeline.md``.
    """
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        areas=["pipe"],
    )
    lines, note, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" not in lines
    assert coverage == "unmapped"
    assert "pipe" in note


def test_hyphenation_normalizes_both_sides(tmp_path):
    """Spec R7's second trap: ``overnight-runner`` selects ``pipeline.md``.

    The retired selector matched ``overnight runner`` but not the hyphenated
    form the index actually carries.
    """
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("pipeline, overnight runner, deferral", "cortex/requirements/pipeline.md"),
        ],
        areas=["overnight-runner"],
    )
    lines, _, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines
    assert coverage == "loaded"


def test_underscores_and_case_normalize(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("Remote Access, Tailscale", "cortex/requirements/remote-access.md")],
        areas=["remote_access"],
    )
    lines, _, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/remote-access.md" in lines
    assert coverage == "loaded"


def test_tags_are_inert(tmp_path):
    """``tags:`` stays on the index but no longer drives selection."""
    idx_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    _write_repo(tmp_path,
                conditional=[("pipeline", "cortex/requirements/pipeline.md")])
    idx_dir.mkdir(parents=True, exist_ok=True)
    (idx_dir / "index.md").write_text(
        '---\ntags: ["pipeline"]\n---\n', encoding="utf-8"
    )
    lines, _, coverage = resolve(tmp_path, "feat")
    assert "cortex/requirements/pipeline.md" not in lines
    assert coverage == "no-area"


# ---------------------------------------------------------------------------
# Coverage tiers
# ---------------------------------------------------------------------------

def test_doc_missing_names_area_and_path(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("lifecycle", "cortex/requirements/lifecycle.md")],
        areas=["lifecycle"],
        touch_paths=False,  # the mapped doc does not exist yet
    )
    lines, note, coverage = resolve(tmp_path, slug)
    assert coverage == "doc-missing"
    assert "cortex/requirements/lifecycle.md (skipped: file absent)" in lines
    assert "lifecycle" in note and "cortex/requirements/lifecycle.md" in note


def test_loaded_outranks_a_missing_sibling_doc(tmp_path):
    """One good doc means the drift check has something to run against."""
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("pipeline", "cortex/requirements/pipeline.md"),
            ("lifecycle", "cortex/requirements/lifecycle.md"),
        ],
        areas=["pipeline", "lifecycle"],
        touch_paths=False,
    )
    _touch(tmp_path, "cortex/requirements/pipeline.md")
    _, note, coverage = resolve(tmp_path, slug)
    assert coverage == "loaded"
    assert note is None


def test_unmapped_is_one_terse_line(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        areas=["skills", "hooks", "tests"],
    )
    proc = _run(tmp_path, "--feature", slug)
    assert proc.returncode == 0
    stderr_lines = proc.stderr.splitlines()
    assert len(stderr_lines) == 2, proc.stderr  # one detail line + one marker
    assert _marker_lines(proc.stderr) == ["COVERAGE:unmapped"]


def test_every_run_emits_exactly_one_marker(tmp_path):
    """Four fixture runs, one per state, default invocation, no flags."""
    cases = {
        "loaded": dict(areas=["pipeline"], touch_paths=True),
        "doc-missing": dict(areas=["pipeline"], touch_paths=False),
        "unmapped": dict(areas=["skills"], touch_paths=True),
        "no-area": dict(areas=[], touch_paths=True),
    }
    for expected, kwargs in cases.items():
        root = tmp_path / expected
        slug = _write_repo(
            root,
            conditional=[("pipeline", "cortex/requirements/pipeline.md")],
            **kwargs,
        )
        proc = _run(root, "--feature", slug)
        assert proc.returncode == 0, proc.stderr
        assert _marker_lines(proc.stderr) == [f"COVERAGE:{expected}"], (
            expected, proc.stderr
        )
        # stdout keeps HEAD's shape: paths only, project.md first.
        out = proc.stdout.splitlines()
        assert out[0] == "cortex/requirements/project.md"
        for line in out:
            assert _is_path_line(line), (expected, line)


def test_no_stderr_string_claims_project_md_only(tmp_path):
    """Spec R10: ``glossary.md`` is Global Context and loads on the fallback."""
    cases = ((None, True), ([], True), (["skills"], True), (["pipeline"], False))
    for i, (areas, touch) in enumerate(cases):
        root = tmp_path / f"case{i}"
        slug = _write_repo(
            root,
            conditional=[("pipeline", "cortex/requirements/pipeline.md")],
            global_context=["cortex/requirements/glossary.md"],
            areas=areas, touch_paths=touch,
        )
        proc = _run(root, "--feature", slug)
        assert "loaded project.md only" not in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# R5 — output shape + dedup position
# ---------------------------------------------------------------------------

def _is_path_line(line):
    # The COVERAGE marker is space-free and equals its own strip, so it would
    # otherwise satisfy both clauses below and pass as a path. Rejecting it
    # explicitly is what lets these assertions catch a marker *duplicated* onto
    # stdout while stderr still carries it — a move is caught by the stderr
    # assertions, but a duplication is invisible without this line (#333/#472).
    return (
        not line.startswith(COVERAGE_MARKER_PREFIX)
        and line == line.strip()
        and (line.endswith(" (skipped: file absent)") or " " not in line)
    )


def test_first_line_is_project_md(tmp_path):
    _write_repo(tmp_path, conditional=[("a", "cortex/requirements/a.md")])
    lines, _, _ = resolve(tmp_path, None)
    assert lines[0] == "cortex/requirements/project.md"


def test_stdout_is_paths_only(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        global_context=["cortex/requirements/glossary.md"],  # absent → skip-suffix
        areas=["pipeline"],
        touch_paths=False,
    )
    lines, _, _ = resolve(tmp_path, slug)
    for line in lines:
        assert _is_path_line(line), f"non-path line: {line!r}"


def test_dedup_global_context_position_wins(tmp_path):
    # A path that is BOTH a Global Context entry AND an area-matched doc is
    # emitted ONCE, in its Global Context position (right after project.md),
    # not appended after — assert position via a full ordered golden.
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/shared.md")],
        global_context=["cortex/requirements/shared.md"],
        areas=["pipeline"],
    )
    lines, _, _ = resolve(tmp_path, slug)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/shared.md",
    ]


# ---------------------------------------------------------------------------
# R6 — goldens + note strings (independent literals) + live oracle
# ---------------------------------------------------------------------------

def test_golden_match(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("statusline, dashboard", "cortex/requirements/observability.md"),
            ("pipeline", "cortex/requirements/pipeline.md"),
        ],
        global_context=["cortex/requirements/glossary.md"],
        areas=["pipeline"],
        touch_paths=True,
    )
    lines, note, coverage = resolve(tmp_path, slug)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/glossary.md",
        "cortex/requirements/pipeline.md",
    ]
    assert note is None
    assert coverage == "loaded"


def test_golden_fallback_empty(tmp_path):
    _write_repo(tmp_path, conditional=[("a", "cortex/requirements/a.md")],
                global_context=["cortex/requirements/glossary.md"])
    lines, note, coverage = resolve(tmp_path, None)
    assert lines == [
        "cortex/requirements/project.md",
        "cortex/requirements/glossary.md",
    ]
    assert note == EXPECTED_FALLBACK
    assert coverage == "no-area"


def test_unmapped_note_single_and_multi(tmp_path):
    slug1 = _write_repo(tmp_path / "s", conditional=[("x", "cortex/requirements/x.md")],
                        areas=["foo"])
    _, note1, cov1 = resolve(tmp_path / "s", slug1)
    assert cov1 == "unmapped"
    assert note1 == "no area doc is mapped for foo — expected for areas that have none"

    slug2 = _write_repo(tmp_path / "m", conditional=[("x", "cortex/requirements/x.md")],
                        areas=["foo", "bar"])
    _, note2, cov2 = resolve(tmp_path / "m", slug2)
    assert cov2 == "unmapped"
    assert note2 == (
        "no area doc is mapped for foo, bar — expected for areas that have none"
    )
    assert len(note2.splitlines()) == 1


def test_dedup_multi_area_one_row(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("statusline, dashboard, notifications",
                      "cortex/requirements/observability.md")],
        areas=["statusline", "dashboard"],
    )
    lines, _, _ = resolve(tmp_path, slug)
    assert lines.count("cortex/requirements/observability.md") == 1


def test_unmatched_area_dropped(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[
            ("observability", "cortex/requirements/observability.md"),
            ("pipeline", "cortex/requirements/pipeline.md"),
        ],
        areas=["nonexistent", "pipeline"],
    )
    lines, _, coverage = resolve(tmp_path, slug)
    assert "cortex/requirements/pipeline.md" in lines
    assert "cortex/requirements/observability.md" not in lines
    assert coverage == "loaded"  # one real doc outranks the unmapped area


def test_live_project_md_format_invariants():
    # Format-realism: the live project.md carries multi-key map rows the
    # synthetic fixtures don't. Drift-robust invariants only.
    lines, _, _ = resolve(REPO_ROOT, None)
    assert lines[0] == "cortex/requirements/project.md"
    for line in lines:
        assert _is_path_line(line), f"non-path line: {line!r}"


def test_live_conditional_loading_paths_are_bare_tokens():
    """Spec R5: every live map row yields a bare repo-relative path.

    The live defect this replaces: the ``lifecycle`` row's trailing editorial
    parenthetical was absorbed into the path, yielding a 180-character string
    that could never resolve.
    """
    from cortex_command.lifecycle.load_requirements_cli import (
        _parse_conditional_loading,
        _split_keys,
    )
    text = (REPO_ROOT / "cortex/requirements/project.md").read_text(encoding="utf-8")
    pairs = _parse_conditional_loading(text)
    assert pairs, "no Conditional Loading rows parsed from live project.md"
    for key_text, path in pairs:
        assert path.startswith("cortex/requirements/"), (key_text, path)
        assert " " not in path, (key_text, path)
        assert ARROW_LITERAL not in key_text and ARROW_LITERAL not in path
    # at least one row carries a multi-key list — the realistic map format.
    assert any(len(_split_keys(keys)) > 1 for keys, _ in pairs)


def test_live_map_covers_the_spec_key_set():
    """Spec R6: the derived key set is a superset of the enumerated synonyms."""
    from cortex_command.lifecycle.load_requirements_cli import (
        _parse_conditional_loading,
        _split_keys,
    )
    text = (REPO_ROOT / "cortex/requirements/project.md").read_text(encoding="utf-8")
    keys = {k for key_text, _ in _parse_conditional_loading(text)
            for k in _split_keys(key_text)}
    required = {
        "pipeline", "overnight-runner", "conflict-resolution", "deferral",
        "statusline", "dashboard", "notifications", "remote-access", "tmux",
        "mosh", "tailscale", "agent-spawning", "subagents", "multi-agent",
        "parallel-dispatch", "worktrees", "model-selection", "backlog",
        "ticketing", "issue-tracker", "backlog-backend", "training",
        "workshop", "presentation", "scene-deck",
        # the bare key 44 tickets declare, absent from the retired trigger list
        "lifecycle",
    }
    assert required <= keys, sorted(required - keys)


def test_live_project_md_selection_oracle(tmp_path):
    # Selection oracle over the LIVE project.md map, drift-robust: the expected
    # pick is COMPUTED from the live file at test time (not frozen), so a
    # future project.md edit cannot produce a false RED. Copy live project.md
    # into a tmp repo so a synthetic index can attach without polluting the
    # real repo.
    from cortex_command.lifecycle.load_requirements_cli import (
        _parse_conditional_loading,
        _split_keys,
    )
    live = (REPO_ROOT / "cortex/requirements/project.md").read_text(encoding="utf-8")
    pairs = _parse_conditional_loading(live)
    assert pairs, "live project.md has no Conditional Loading rows"
    key_text, path = pairs[0]
    key = _split_keys(key_text)[0]

    req = tmp_path / "cortex" / "requirements"
    req.mkdir(parents=True)
    (req / "project.md").write_text(live, encoding="utf-8")
    _touch(tmp_path, path)  # the selected area doc exists → no skip-suffix
    idx = tmp_path / "cortex" / "lifecycle" / "live"
    idx.mkdir(parents=True)
    (idx / "index.md").write_text(f'---\nareas: ["{key}"]\n---\n', encoding="utf-8")

    lines, note, coverage = resolve(tmp_path, "live")
    assert path in lines, f"area {key!r} (from live row {key_text!r}) selects {path}"
    assert note is None
    assert coverage == "loaded"


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
    lines, _, _ = resolve(tmp_path, None)
    assert "cortex/requirements/glossary.md (skipped: file absent)" in lines


# ---------------------------------------------------------------------------
# R7 — no events emission (behavioral)
# ---------------------------------------------------------------------------

def test_verb_writes_no_events_log(tmp_path):
    slug = _write_repo(
        tmp_path,
        conditional=[("pipeline", "cortex/requirements/pipeline.md")],
        areas=["pipeline"],
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
