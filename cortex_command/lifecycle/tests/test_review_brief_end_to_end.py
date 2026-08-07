"""End-to-end proof that the rework-scoped review path actually runs.

Pins requirement 20 of ``cortex/lifecycle/a-rework-re-review-re-reads/spec.md``.
Every other criterion in this feature certifies that one artifact exists and
behaves in isolation — none of them would fail if the scoped path never ran at
all. This module closes that hole by driving a throwaway lifecycle through the
real sequence:

    cycle-1 dispatch → CHANGES_REQUESTED verdict with a 3-issue review.md
                     → rework commit → cycle-2 dispatch

and asserting on what the *shipped* binaries produced.

Two disciplines make the proof non-vacuous.

**The real wrapper, not the module.** Dispatch goes through
``bin/cortex-lifecycle-review-brief`` as a subprocess with
``CORTEX_COMMAND_FORCE_SOURCE=1``. ``cortex-*`` on PATH is the *released wheel*,
so an unforced invocation would silently certify a different build than the
working tree. The verdict row likewise comes from the real
``bin/cortex-lifecycle-advance review-verdict`` rather than a hand-written
events.log line, so ``count_rework_cycles`` reads a row this test did not author.

**The fixture's shape is taken from the shipped prose.** The Verdict block in
the review.md this test writes carries the info string that
``skills/build/references/review.md`` actually prescribes, read out of that file
at runtime — not the one that is convenient here. That coupling is deliberate:
the prose once prescribed a *bare* fence while ``parse_verdict_block`` requires
a ```` ```json ````-labelled one, so every interactive rework degraded to a full
brief with all of this feature's other tests green. Under that prose this
module's cycle-2 dispatch degrades (exit 3, unscoped brief) and fails.

Marked ``serial``: each test in the driven flow spawns real subprocesses.
Nothing touches the repo's own ``cortex/`` — the lifecycle, the git repo, and
``HOME`` all live under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.serial


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BRIEF_SHIM = REPO_ROOT / "bin" / "cortex-lifecycle-review-brief"
ADVANCE_SHIM = REPO_ROOT / "bin" / "cortex-lifecycle-advance"
REVIEW_PROSE = REPO_ROOT / "skills" / "build" / "references" / "review.md"

requires_shims = pytest.mark.skipif(
    not (BRIEF_SHIM.is_file() and ADVANCE_SHIM.is_file() and REVIEW_PROSE.is_file()),
    reason="working-tree bin/ shims or shipped review prose not present",
)

SLUG = "end-to-end-scoped-path"

# The three issue texts the cycle-1 verdict carries. Distinctive enough that
# finding one in the cycle-2 brief cannot be a coincidental substring match.
ISSUES = [
    "SENTINEL-ALPHA the archive was moved rather than copied",
    "SENTINEL-BRAVO the dispatch baseline row is absent",
    "SENTINEL-CHARLIE the checklist section carries no disposition",
]

CARRIED_REQUIREMENT = "R7 — the loader reads every listed path"

_SHA = re.compile(r"\b[0-9a-f]{40}\b")


# --- harness ----------------------------------------------------------------


def _base_env(home: Path, shim_dir: Path) -> dict:
    """A hermetic environment for the shipped bash wrappers.

    ``PATH`` carries only the python3 shim plus the system directories, so
    ``cortex-log-invocation`` is absent and the wrappers skip their telemetry
    branch. ``HOME`` is a throwaway (``_telemetry`` writes its breadcrumb under
    ``~/.cache``), ``CORTEX_REPO_ROOT`` and ``LIFECYCLE_SESSION_ID`` are unset,
    and the git config files are neutralised so a developer's global
    ``core.hooksPath`` cannot fire this repo's hooks inside ``tmp_path``.
    """
    return {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "CORTEX_COMMAND_FORCE_SOURCE": "1",
        "CORTEX_COMMAND_ROOT": str(REPO_ROOT),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }


def _python3_shim(shim_dir: Path) -> None:
    """Put a ``python3`` on PATH that execs the interpreter running pytest.

    The wrappers invoke bare ``python3``; the first one on a developer's PATH is
    typically a system interpreter without this project's dependencies. A
    two-line ``exec`` script rather than a symlink is deliberate — a symlink into
    a venv resolves through to the base interpreter and loses the venv's
    site-packages, which is exactly the import failure this avoids.
    """
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)


def _run(args: list[str], cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120
    )


def _git(args: list[str], cwd: Path, env: dict) -> str:
    proc = _run(["git"] + args, cwd, env)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict_fence_info() -> str:
    """The info string the shipped review prose prescribes for the Verdict block.

    Reads ``skills/build/references/review.md``, finds the Verdict-contract
    marker, and returns the info string of the first fenced block after it — an
    empty string for a bare ```` ``` ```` fence. Asserts the marker is present
    rather than defaulting, so a restructured prose file fails loudly instead of
    letting this module fall back to a convenient shape of its own.
    """
    text = REVIEW_PROSE.read_text(encoding="utf-8")
    marker = text.find("**Verdict contract**")
    assert marker != -1, f"no '**Verdict contract**' marker in {REVIEW_PROSE}"
    fence = re.search(r"^```(.*)$", text[marker:], re.MULTILINE)
    assert fence is not None, f"no fenced block after the Verdict contract in {REVIEW_PROSE}"
    return fence.group(1).strip()


def _review_md(fence_info: str) -> str:
    """A cycle-1 review artifact in the shape the shipped prose prescribes."""
    verdict = json.dumps(
        {
            "verdict": "CHANGES_REQUESTED",
            "cycle": 1,
            "issues": ISSUES,
            "requirements_drift": "none",
        },
        indent=2,
    )
    return (
        "# Review — cycle 1\n\n"
        f"### Requirement: {CARRIED_REQUIREMENT}\n\n"
        "PASS — carried forward from cycle 0; holds while the loader's path list is unchanged\n\n"
        "## Requirements Drift\n\n"
        "- **State**: none\n"
        "- **Findings**: None\n"
        "- **Update needed**: None\n\n"
        f"```{fence_info}\n{verdict}\n```\n"
    )


@pytest.fixture(scope="module")
def flow(tmp_path_factory) -> SimpleNamespace:
    """Drive one lifecycle from cycle-1 dispatch to cycle-2 dispatch.

    Module-scoped: the sequence is one causal chain (each step's input is the
    previous step's on-disk effect), so it runs once and the assertions below
    read its recorded observations.
    """
    if not (BRIEF_SHIM.is_file() and ADVANCE_SHIM.is_file() and REVIEW_PROSE.is_file()):
        pytest.skip("working-tree bin/ shims or shipped review prose not present")

    base = tmp_path_factory.mktemp("scoped-path")
    home = base / "home"
    home.mkdir()
    env = _base_env(home, base / "shim")
    _python3_shim(base / "shim")

    root = (base / "proj").resolve()
    feature_dir = root / "cortex" / "lifecycle" / SLUG
    feature_dir.mkdir(parents=True)
    events_log = feature_dir / "events.log"
    review_md = feature_dir / "review.md"

    _git(["init", "-b", "main", "."], root, env)
    (root / "src.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(["add", "src.py"], root, env)
    _git(["commit", "-m", "Seed"], root, env)
    seed_sha = _git(["rev-parse", "HEAD"], root, env)

    # The lifecycle is in review: the state guard on the review-verdict verb
    # routes from this transition, and review.md does not exist yet.
    events_log.write_text(
        json.dumps(
            {
                "ts": "2026-08-07T00:00:00Z",
                "event": "phase_transition",
                "feature": SLUG,
                "from": "implement",
                "to": "review",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    dispatch1 = _run([str(BRIEF_SHIM), "--feature", SLUG], root, env)

    # The reviewer's cycle-1 output, shaped by the shipped prose.
    fence_info = verdict_fence_info()
    review_md.write_text(_review_md(fence_info), encoding="utf-8")
    pre_dispatch_digest = _sha256(review_md)
    pre_dispatch_bytes = review_md.read_bytes()

    verdict = _run(
        [
            str(ADVANCE_SHIM),
            "review-verdict",
            "--feature",
            SLUG,
            "--verdict",
            "CHANGES_REQUESTED",
            "--cycle",
            "1",
            "--drift",
            "none",
        ],
        root,
        env,
    )

    # The rework itself: a source change outside the lifecycle directory, so the
    # cycle-2 brief must decide re-run rather than reuse.
    (root / "src.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    _git(["add", "src.py"], root, env)
    _git(["commit", "-m", "Rework the flagged behavior"], root, env)
    rework_sha = _git(["rev-parse", "HEAD"], root, env)

    dispatch2 = _run([str(BRIEF_SHIM), "--feature", SLUG], root, env)

    return SimpleNamespace(
        root=root,
        env=env,
        feature_dir=feature_dir,
        events_log=events_log,
        review_md=review_md,
        archive=feature_dir / "review-cycle-1.md",
        seed_sha=seed_sha,
        rework_sha=rework_sha,
        fence_info=fence_info,
        pre_dispatch_digest=pre_dispatch_digest,
        pre_dispatch_bytes=pre_dispatch_bytes,
        dispatch1=dispatch1,
        verdict=verdict,
        dispatch2=dispatch2,
    )


def _events(flow: SimpleNamespace) -> list[dict]:
    rows = []
    for line in flow.events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# --- the flow ---------------------------------------------------------------


@requires_shims
def test_cycle_one_dispatch_serves_a_full_brief_and_records_its_baseline(flow):
    """Cycle 1 has no prior cycle: a full brief, and a baseline row at HEAD."""
    assert flow.dispatch1.returncode == 0, flow.dispatch1.stderr
    assert "cycle 1 · full review" in flow.dispatch1.stdout
    assert "## Prior-cycle checklist" not in flow.dispatch1.stdout

    dispatched = [r for r in _events(flow) if r.get("event") == "review_dispatched"]
    cycle1 = [r for r in dispatched if r.get("cycle") == 1]
    assert len(cycle1) == 1, dispatched
    assert cycle1[0]["mode"] == "full"
    assert cycle1[0]["baseline_sha"] == flow.seed_sha


@requires_shims
def test_the_verdict_verb_routes_the_lifecycle_into_rework(flow):
    """The rework count the cycle-2 dispatch reads is written by the real verb."""
    assert flow.verdict.returncode == 0, flow.verdict.stderr
    assert json.loads(flow.verdict.stdout)["state"] == "rework"

    rows = _events(flow)
    assert any(
        r.get("event") == "review_verdict" and r.get("verdict") == "CHANGES_REQUESTED"
        for r in rows
    ), rows
    assert any(
        r.get("event") == "phase_transition" and r.get("to") == "implement-rework"
        for r in rows
    ), rows


@requires_shims
def test_cycle_two_dispatch_archives_the_prior_review_byte_for_byte(flow):
    """``review-cycle-1.md`` is a copy of what was on disk before dispatch."""
    assert flow.archive.is_file(), sorted(p.name for p in flow.feature_dir.iterdir())
    assert _sha256(flow.archive) == flow.pre_dispatch_digest
    assert flow.archive.read_bytes() == flow.pre_dispatch_bytes

    # Copy, never move: a window without review.md makes phase detection report
    # ``review`` instead of ``implement-rework``.
    assert flow.review_md.is_file()
    assert flow.review_md.read_bytes() == flow.pre_dispatch_bytes


@requires_shims
def test_cycle_two_brief_is_scoped_and_carries_the_prior_cycle_issues(flow):
    """The scoped brief actually ran — exit 0, rework mode, real issue text."""
    assert flow.dispatch2.returncode == 0, (
        f"expected a scoped brief, got exit {flow.dispatch2.returncode}: "
        f"{flow.dispatch2.stderr}"
    )
    assert "DEGRADED" not in flow.dispatch2.stderr

    brief = flow.dispatch2.stdout
    assert "cycle 2 · rework re-review (scoped)" in brief
    assert "## Prior-cycle checklist" in brief
    assert "## Out-of-scope findings" in brief
    for issue in ISSUES:
        assert issue in brief, f"cycle-1 issue missing from the cycle-2 brief: {issue}"

    # The carry-forward bound reached the brief from the archive's own prose.
    assert CARRIED_REQUIREMENT in brief
    # A source file outside the lifecycle directory changed.
    assert "Decision: **re-run**" in brief


@requires_shims
def test_cycle_two_brief_names_a_sha_that_resolves_in_the_repo(flow):
    """The reading range opens at a commit the reviewer can actually check out."""
    brief = flow.dispatch2.stdout
    shas = _SHA.findall(brief)
    assert shas, f"no 40-hex SHA in the cycle-2 brief:\n{brief}"

    sha = shas[0]
    assert f"`{sha}..HEAD`" in brief
    resolved = _git(["rev-parse", "--verify", f"{sha}^{{commit}}"], flow.root, flow.env)
    assert resolved == sha

    # It is the cycle-1 dispatch baseline, and the range it opens is non-empty:
    # a range that resolves but contains nothing would scope the reviewer to no
    # commits at all.
    assert sha == flow.seed_sha
    assert sha != flow.rework_sha
    revs = _git(["rev-list", f"{sha}..HEAD"], flow.root, flow.env).split()
    assert revs == [flow.rework_sha]

    dispatched = [
        r
        for r in _events(flow)
        if r.get("event") == "review_dispatched" and r.get("cycle") == 2
    ]
    assert len(dispatched) == 1, dispatched
    assert dispatched[0]["mode"] == "rework"
    assert dispatched[0]["baseline_sha"] == flow.rework_sha


# --- the coupling that keeps the flow above honest --------------------------


@requires_shims
def test_shipped_prose_prescribes_the_fence_the_parser_requires():
    """The prose's Verdict fence must be the one ``parse_verdict_block`` reads.

    Stated directly as well as exercised through the flow: a bare fence here is
    the defect that made every interactive rework degrade to a full brief while
    every other test in this feature stayed green.
    """
    from cortex_command.lifecycle.review_brief import parse_verdict_block

    info = verdict_fence_info()
    assert info == "json", (
        f"{REVIEW_PROSE} prescribes a ```{info} fence for the Verdict block, "
        "but parse_verdict_block only reads ```json"
    )
    parsed = parse_verdict_block(_review_md(info))
    assert parsed is not None and parsed["issues"] == ISSUES
