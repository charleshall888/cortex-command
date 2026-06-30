"""Tests for ``cortex_command.lifecycle.resolve_model_cli`` (cortex-resolve-model).

Four in-process test groups plus a subprocess smoke test:

  (a) table-coverage — every value-bearing cell of the Lifecycle Matrix
      (spec #334 Req 3) resolves to the expected model.
  (b) fail-loud — unknown role, an undefined (role, criticality) cell, and a
      tier-keyed role with --criticality omitted all exit 2, emitting nothing
      on stdout (no silent default).
  (c) role-threshold regression — the discriminator that makes --role
      mandatory (orchestrator-fix@high=sonnet vs review@high=opus) plus the
      three highest-stakes critical cells.
  (d) golden-anchor — the module is asserted equal, cell-for-cell, to the
      Lifecycle Matrix parsed independently out of the live
      ``skills/lifecycle/assets/model-selection.md`` (today's actual source),
      so a transcription error in the module's inline matrix is caught against
      something other than a same-change restatement.

The golden-anchor parse lives behind ``_expected_matrix_from_model_selection_md``
so Phase 3 can swap it for a frozen literal once the parse has proven the
module reproduces the source (after which model-selection.md is deleted).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from cortex_command.lifecycle.resolve_model_cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_SELECTION_MD = (
    REPO_ROOT / "skills" / "lifecycle" / "assets" / "model-selection.md"
)

CRITICALITY_COLUMNS = ["low", "medium", "high", "critical"]
_MODELS = {"haiku", "sonnet", "opus"}
_ALL_ROLES = ("review", "builder", "orchestrator-fix", "competing-plan", "synthesizer")

# model-selection.md row label -> module role. Matched CASE-INSENSITIVELY:
# both these keys and the parsed cell labels are casefolded before lookup, so a
# capitalization mismatch cannot silently yield zero matches and a vacuous pass.
_ROW_LABEL_TO_ROLE = {
    "Review sub-task": "review",
    "Builder sub-task": "builder",
    "Orchestrator fix dispatch": "orchestrator-fix",
    "Competing plan agents": "competing-plan",
}
# Orphan rows present in the table but NOT modeled by the verb (Non-Requirements).
_SKIP_LABELS = {"codebase exploration", "parallel research agents"}


# ---------------------------------------------------------------------------
# In-process runner — handles both return-int and argparse SystemExit exits.
# ---------------------------------------------------------------------------


def _run(argv, capsys):
    """Invoke main(argv) in-process; return (exit_code, stdout, stderr)."""
    try:
        code = main(argv)
    except SystemExit as exc:  # argparse rejects invalid choices this way
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# (a) Table-coverage — every explicit value-bearing cell (spec Req 3).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,criticality,model",
    [
        ("review", "low", "sonnet"),
        ("review", "medium", "sonnet"),
        ("review", "high", "opus"),
        ("review", "critical", "opus"),
        ("builder", "low", "sonnet"),
        ("builder", "medium", "sonnet"),
        ("builder", "high", "opus"),
        ("builder", "critical", "opus"),
        ("orchestrator-fix", "low", "sonnet"),
        ("orchestrator-fix", "medium", "sonnet"),
        ("orchestrator-fix", "high", "sonnet"),
        ("orchestrator-fix", "critical", "opus"),
        ("competing-plan", "critical", "sonnet"),
    ],
)
def test_table_coverage(role, criticality, model, capsys):
    code, out, _ = _run(["--role", role, "--criticality", criticality], capsys)
    assert code == 0, f"{role}/{criticality}: expected exit 0, got {code}"
    assert out == model + "\n", f"{role}/{criticality}: expected {model!r}, got {out!r}"


def test_synthesizer_is_constant_opus(capsys):
    """synthesizer is criticality-independent: opus with or without --criticality."""
    for argv in (
        ["--role", "synthesizer"],
        ["--role", "synthesizer", "--criticality", "low"],
        ["--role", "synthesizer", "--criticality", "critical"],
    ):
        code, out, _ = _run(argv, capsys)
        assert code == 0, f"{argv}: expected exit 0, got {code}"
        assert out == "opus\n", f"{argv}: expected 'opus', got {out!r}"


# ---------------------------------------------------------------------------
# (b) Fail-loud — never default; emit nothing on stdout for bad input.
# ---------------------------------------------------------------------------


def test_unknown_role_exits_2_and_lists_valid_roles(capsys):
    code, out, err = _run(["--role", "bogus", "--criticality", "high"], capsys)
    assert code == 2
    assert out == ""
    for role in _ALL_ROLES:
        assert role in err, f"stderr should name valid role {role!r}: {err!r}"


def test_competing_plan_undefined_cell_exits_2(capsys):
    """competing-plan is critical-only; low/medium/high are undefined cells."""
    code, out, _ = _run(["--role", "competing-plan", "--criticality", "low"], capsys)
    assert code == 2
    assert out == ""


def test_tier_keyed_role_missing_criticality_exits_2(capsys):
    code, out, _ = _run(["--role", "review"], capsys)
    assert code == 2
    assert out == ""


def test_unknown_criticality_exits_2(capsys):
    code, out, _ = _run(["--role", "review", "--criticality", "bogus"], capsys)
    assert code == 2
    assert out == ""


# ---------------------------------------------------------------------------
# (c) Role-threshold regression — the discriminator + the critical cells.
# ---------------------------------------------------------------------------


def test_role_threshold_discriminator_at_high(capsys):
    """At high, orchestrator-fix=sonnet but review=opus — the role threshold."""
    code, out, _ = _run(["--role", "orchestrator-fix", "--criticality", "high"], capsys)
    assert code == 0 and out == "sonnet\n", f"orchestrator-fix@high: got {out!r}"
    code, out, _ = _run(["--role", "review", "--criticality", "high"], capsys)
    assert code == 0 and out == "opus\n", f"review@high: got {out!r}"


@pytest.mark.parametrize("role", ["orchestrator-fix", "review", "builder"])
def test_highest_stakes_critical_cells_are_opus(role, capsys):
    code, out, _ = _run(["--role", role, "--criticality", "critical"], capsys)
    assert code == 0 and out == "opus\n", f"{role}@critical: got {out!r}"


# ---------------------------------------------------------------------------
# (d) Golden anchor — parse model-selection.md independently and compare.
# ---------------------------------------------------------------------------


def _split_markdown_row(line):
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _strip_md(cell):
    """Strip markdown emphasis/backticks; preserve case for casefold control."""
    return re.sub(r"[*_`]", "", cell).strip()


def _is_separator_row(cells):
    return all(re.fullmatch(r":?-{1,}:?", c.strip()) for c in cells if c.strip())


def _expected_matrix_from_model_selection_md():
    """Parse the Lifecycle Matrix out of model-selection.md as ground truth.

    Returns ``{role: {criticality: model_or_None}}`` for the four roles the verb
    models (the two orphan rows are skipped); a ``None`` value marks a ``—``
    (undefined) cell, which the module must reject with exit 2. Phase 3 swaps
    this helper for a frozen literal once the parse has proven module == source.
    """
    assert MODEL_SELECTION_MD.is_file(), (
        f"model-selection.md not found at {MODEL_SELECTION_MD}; the "
        "golden-anchor source for the Lifecycle Matrix is missing."
    )
    lines = MODEL_SELECTION_MD.read_text(encoding="utf-8").splitlines()

    # Locate the Lifecycle Matrix header row (all four criticality columns).
    header_idx = None
    col_index = None
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = [_strip_md(c).lower() for c in _split_markdown_row(line)]
        positions = {}
        for crit in CRITICALITY_COLUMNS:
            for pos, cell in enumerate(cells):
                if cell == crit:
                    positions[crit] = pos
                    break
        if len(positions) == len(CRITICALITY_COLUMNS):
            header_idx = i
            col_index = positions
            break
    assert header_idx is not None, (
        f"Could not find the Lifecycle Matrix header row in {MODEL_SELECTION_MD}."
    )

    label_to_role = {k.casefold(): v for k, v in _ROW_LABEL_TO_ROLE.items()}
    expected = {}
    for line in lines[header_idx + 1:]:
        if "|" not in line:
            if line.strip() == "":
                continue
            break  # a non-table line (e.g. the next ## heading) ends the table
        cells = _split_markdown_row(line)
        if _is_separator_row(cells):
            continue
        label = _strip_md(cells[0]).casefold()
        if label in _SKIP_LABELS:
            continue
        role = label_to_role.get(label)
        if role is None:
            continue
        row = {}
        for crit in CRITICALITY_COLUMNS:
            pos = col_index[crit]
            raw = _strip_md(cells[pos]).lower()
            row[crit] = raw if raw in _MODELS else None
        expected[role] = row
    return expected


def test_golden_anchor_matches_parsed_model_selection_md(capsys):
    """Module output equals the live model-selection.md Lifecycle Matrix."""
    expected = _expected_matrix_from_model_selection_md()
    # The four migrated rows were actually found — a zero-match cannot pass.
    assert set(expected) == {
        "review",
        "builder",
        "orchestrator-fix",
        "competing-plan",
    }, f"parsed roles {sorted(expected)} != the four migrated rows"

    for role, row in expected.items():
        assert len(row) == len(CRITICALITY_COLUMNS), f"{role}: incomplete row {row}"
        for criticality, model in row.items():
            code, out, _ = _run(
                ["--role", role, "--criticality", criticality], capsys
            )
            if model is None:
                # A '—' cell must be an undefined cell in the module.
                assert code == 2, (
                    f"{role}/{criticality}: model-selection.md has '—' but the "
                    f"module did not exit 2 (got {code}, out={out!r})"
                )
            else:
                assert code == 0 and out == model + "\n", (
                    f"{role}/{criticality}: model-selection.md says {model!r} "
                    f"but module gave code={code} out={out!r}"
                )

    # synthesizer has no Lifecycle Matrix row — it is pinned by the verb's own
    # contract, not the parsed table, so it is asserted separately.
    code, out, _ = _run(["--role", "synthesizer"], capsys)
    assert code == 0 and out == "opus\n"


# ---------------------------------------------------------------------------
# Subprocess smoke — names the console command `cortex-resolve-model`, which is
# the in-scope (tests/**) parity wiring signal (a matrix table cell would not
# count). Invokes the binstub with CORTEX_COMMAND_FORCE_SOURCE=1 so it works
# pre-reinstall (working-tree branch (a)). Subprocess pattern: test_check_parity.
# ---------------------------------------------------------------------------

BINSTUB = REPO_ROOT / "bin" / "cortex-resolve-model"


def test_cortex_resolve_model_binstub_smoke():
    """`cortex-resolve-model --role synthesizer` → opus via the working-tree binstub."""
    env = dict(os.environ)
    env["CORTEX_COMMAND_FORCE_SOURCE"] = "1"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT}:{existing}" if existing else str(REPO_ROOT)
    result = subprocess.run(
        [str(BINSTUB), "--role", "synthesizer"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"binstub exited {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert result.stdout == "opus\n", f"got {result.stdout!r}"
