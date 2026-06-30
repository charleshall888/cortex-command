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
  (d) golden-anchor — the module is asserted equal, cell-for-cell, to a frozen
      golden matrix transcribed from spec #334 Req 3. This originally parsed the
      live Lifecycle Matrix asset as an independent ground truth; once that parse
      proved module == source the values were frozen into the golden literal
      (and the source asset was deleted), so the anchor now survives without it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.lifecycle.resolve_model_cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]

CRITICALITY_COLUMNS = ["low", "medium", "high", "critical"]
_ALL_ROLES = ("review", "builder", "orchestrator-fix", "competing-plan", "synthesizer", "searcher")


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


def test_searcher_is_constant_sonnet(capsys):
    """searcher is criticality-independent: sonnet with or without --criticality."""
    for argv in (
        ["--role", "searcher"],
        ["--role", "searcher", "--criticality", "low"],
        ["--role", "searcher", "--criticality", "critical"],
    ):
        code, out, _ = _run(argv, capsys)
        assert code == 0, f"{argv}: expected exit 0, got {code}"
        assert out == "sonnet\n", f"{argv}: expected 'sonnet', got {out!r}"


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
# (d) Golden anchor — frozen literal (spec #334 Req 3) compared to the module.
# ---------------------------------------------------------------------------


def _expected_golden_matrix():
    """Frozen golden matrix transcribed from spec #334 Req 3.

    Returns ``{role: {criticality: model_or_None}}`` for the four roles the verb
    models; a ``None`` value marks an undefined cell, which the module must
    reject with exit 2. These literals were proven equal to the original
    Lifecycle Matrix asset by the Phase-1 parse-based assertion before that asset
    was removed, so freezing is safe. Transcribed from the spec's stated cells,
    NOT copied from the module's ``_LIFECYCLE_MATRIX`` — a same-module copy would
    degrade the assertion to a circular module == module.
    """
    return {
        "review": {"low": "sonnet", "medium": "sonnet", "high": "opus", "critical": "opus"},
        "builder": {"low": "sonnet", "medium": "sonnet", "high": "opus", "critical": "opus"},
        "orchestrator-fix": {
            "low": "sonnet",
            "medium": "sonnet",
            "high": "sonnet",
            "critical": "opus",
        },
        "competing-plan": {"low": None, "medium": None, "high": None, "critical": "sonnet"},
    }


def test_golden_anchor_matches_frozen_matrix(capsys):
    """Module output equals the frozen golden Lifecycle Matrix (spec Req 3)."""
    expected = _expected_golden_matrix()
    # The four migrated rows are present — a zero-match cannot pass.
    assert set(expected) == {
        "review",
        "builder",
        "orchestrator-fix",
        "competing-plan",
    }, f"golden roles {sorted(expected)} != the four migrated rows"

    for role, row in expected.items():
        assert len(row) == len(CRITICALITY_COLUMNS), f"{role}: incomplete row {row}"
        for criticality, model in row.items():
            code, out, _ = _run(
                ["--role", role, "--criticality", criticality], capsys
            )
            if model is None:
                # An undefined cell must exit 2 in the module.
                assert code == 2, (
                    f"{role}/{criticality}: golden matrix has an undefined cell "
                    f"but the module did not exit 2 (got {code}, out={out!r})"
                )
            else:
                assert code == 0 and out == model + "\n", (
                    f"{role}/{criticality}: golden matrix says {model!r} "
                    f"but module gave code={code} out={out!r}"
                )

    # synthesizer has no Lifecycle Matrix row — it is pinned by the verb's own
    # contract, not the golden table, so it is asserted separately.
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
