"""Calibration cross-check for ``bin/cortex-measure-l1-surface``.

Independently parses ``skills/<name>/SKILL.md`` frontmatter via
``yaml.safe_load`` for three skills covering distinct YAML scalar forms,
computes the UTF-8 byte length of ``description`` + ``when_to_use`` the
same way the utility does, then asserts equality with the utility's
emitted row for that skill. Defeats the self-sealing-oracle pattern
flagged by critical review: the utility's correctness is verified
against an external, inline parser invocation rather than against
itself.

Spec: cortex/lifecycle/reduce-boot-context-surface-claudemd-skillmd/spec.md R11.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
UTILITY = REPO_ROOT / "bin" / "cortex-measure-l1-surface"
FRONTMATTER_DELIM = "---"


def _extract_frontmatter(text: str) -> str:
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return ""
    body: list[str] = []
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_DELIM:
            return "\n".join(body)
        body.append(line)
    return ""


def _independent_measure(skill_md: Path) -> int:
    """Re-implement the byte-count via inline yaml.safe_load — external oracle."""
    text = skill_md.read_text(encoding="utf-8")
    fm = _extract_frontmatter(text)
    data = yaml.safe_load(fm) if fm else {}
    assert isinstance(data, dict), f"frontmatter did not parse as mapping: {skill_md}"
    desc = data.get("description") or ""
    wtu = data.get("when_to_use") or ""
    if not isinstance(desc, str):
        desc = str(desc)
    if not isinstance(wtu, str):
        wtu = str(wtu)
    return len(desc.encode("utf-8")) + len(wtu.encode("utf-8"))


def _utility_rows() -> dict[str, int]:
    """Run the utility and parse stdout into ``{skill_name: bytes}``."""
    proc = subprocess.run(
        [str(UTILITY)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, count = parts
        out[name] = int(count)
    return out


# Three skills chosen to exercise distinct YAML scalar forms:
# - commit:          description only (no when_to_use)        — single-line plain
# - critical-review: description + when_to_use (double-quoted escaped form)
# - lifecycle:       description + when_to_use (double-quoted escaped form)
CALIBRATION_SKILLS = ("commit", "lifecycle", "critical-review")


@pytest.mark.parametrize("skill", CALIBRATION_SKILLS)
def test_utility_matches_independent_yaml_parse(skill: str) -> None:
    skill_md = REPO_ROOT / "skills" / skill / "SKILL.md"
    expected = _independent_measure(skill_md)
    rows = _utility_rows()
    assert skill in rows, f"utility output missing row for {skill!r}: {sorted(rows)}"
    assert rows[skill] == expected, (
        f"calibration mismatch for {skill!r}: "
        f"utility={rows[skill]} independent_yaml={expected}"
    )


def test_utility_emits_total_row() -> None:
    rows = _utility_rows()
    assert "total" in rows, f"utility output missing 'total' row: {sorted(rows)}"
    skill_sum = sum(v for k, v in rows.items() if k != "total")
    assert rows["total"] == skill_sum, (
        f"total row {rows['total']} does not equal sum of per-skill rows {skill_sum}"
    )
